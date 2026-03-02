import { API_ENDPOINTS, assertTrustedOAuthUrl } from './config'

export async function getTwitchOAuthUrl(): Promise<string> {
  const response = await fetch(API_ENDPOINTS.auth.twitchOAuth)
  if (!response.ok) {
    throw new Error('Failed to fetch OAuth URL')
  }
  const data = await response.json()
  return assertTrustedOAuthUrl(data.oauth_url, 'twitch')
}

// Note: Uses raw fetch() intentionally — this is the login initiation endpoint.
// Using apiFetch() would trigger the 401 redirect loop on the login page itself.

export async function openTwitchOAuth(): Promise<void> {
  const oauthUrl = await getTwitchOAuthUrl()
  window.location.href = oauthUrl
}
