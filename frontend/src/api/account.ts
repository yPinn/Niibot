import { API_ENDPOINTS } from './config'

export interface LinkedAccount {
  platform: 'twitch' | 'discord'
  platform_user_id: string
  username: string
  created_at: string
}

export async function getLinkedAccounts(): Promise<LinkedAccount[]> {
  const response = await fetch(API_ENDPOINTS.user.linkedAccounts, {
    credentials: 'include',
  })
  if (!response.ok) {
    throw new Error('Failed to fetch linked accounts')
  }
  return response.json()
}

export async function unlinkAccount(platform: 'twitch' | 'discord'): Promise<void> {
  const response = await fetch(API_ENDPOINTS.user.unlinkAccount(platform), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail || 'Failed to unlink account')
  }
}

export async function openOAuthLink(platform: 'twitch' | 'discord'): Promise<void> {
  const endpoint =
    platform === 'twitch' ? API_ENDPOINTS.auth.twitchOAuth : API_ENDPOINTS.auth.discordOAuth

  const response = await fetch(`${endpoint}?mode=link`, { credentials: 'include' })
  if (!response.ok) {
    throw new Error(`Failed to fetch ${platform} OAuth URL`)
  }
  const data = await response.json()
  window.location.href = data.oauth_url
}
