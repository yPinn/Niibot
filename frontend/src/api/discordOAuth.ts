import { API_ENDPOINTS } from './config'

export interface DiscordOAuthStatus {
  enabled: boolean
  message: string
}

export async function getDiscordOAuthStatus(): Promise<DiscordOAuthStatus> {
  const response = await fetch(API_ENDPOINTS.auth.discordStatus)
  if (!response.ok) {
    throw new Error('Failed to fetch Discord OAuth status')
  }
  return response.json()
}

export async function getDiscordOAuthUrl(): Promise<string> {
  const response = await fetch(API_ENDPOINTS.auth.discordOAuth)
  if (!response.ok) {
    if (response.status === 503) {
      throw new Error('Discord OAuth is not configured')
    }
    throw new Error('Failed to fetch Discord OAuth URL')
  }
  const data = await response.json()
  return data.oauth_url
}

export async function openDiscordOAuth(): Promise<void> {
  try {
    const oauthUrl = await getDiscordOAuthUrl()
    window.location.href = oauthUrl
  } catch (error) {
    console.error('Failed to open Discord OAuth:', error)
    throw error
  }
}
