import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'

export type Theme = 'dark' | 'light' | 'system'

export interface User {
  id: string
  name: string
  display_name: string
  avatar: string
  platform: 'twitch' | 'discord'
  theme: Theme
  broadcaster_type: string // "affiliate", "partner", or "" (non-affiliate / discord)
}

async function fetchCurrentUser(): Promise<User | null> {
  // Let network errors propagate — callers distinguish "not logged in" (null)
  // from "couldn't reach the server" (thrown error).
  const response = await apiFetch(API_ENDPOINTS.auth.user, {
    credentials: 'include',
  })

  if (!response.ok) {
    return null
  }

  return await response.json()
}

export async function getCurrentUser(options?: { forceRefresh?: boolean }): Promise<User | null> {
  return apiCache.fetch(CACHE_KEYS.CURRENT_USER, fetchCurrentUser, {
    ttl: 5 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}

export async function updateUserPreferences(prefs: { theme: Theme }): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.user.preferences, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(prefs),
  })
  if (!response.ok) {
    throw new Error('Failed to update preferences')
  }

  // Sync cache so refreshUser() won't return stale theme
  apiCache.patch<User>(CACHE_KEYS.CURRENT_USER, user => ({ ...user, ...prefs }))
}

export async function logout(): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.auth.logout, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error('Failed to logout')
  }
  apiCache.clear()
}
