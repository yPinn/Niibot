import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS } from './config'

export interface User {
  id: string
  name: string
  display_name: string
  avatar: string
  platform: 'twitch' | 'discord'
}

async function fetchCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(API_ENDPOINTS.auth.user, {
      credentials: 'include',
    })

    if (!response.ok) {
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Failed to get user info:', error)
    return null
  }
}

export async function getCurrentUser(options?: { forceRefresh?: boolean }): Promise<User | null> {
  return apiCache.fetch(CACHE_KEYS.CURRENT_USER, fetchCurrentUser, {
    ttl: 5 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}

export async function logout(): Promise<void> {
  try {
    const response = await fetch(API_ENDPOINTS.auth.logout, {
      method: 'POST',
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error('Failed to logout')
    }
    apiCache.clear()
  } catch (error) {
    console.error('Failed to logout:', error)
    throw error
  }
}
