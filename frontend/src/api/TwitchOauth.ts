// Twitch OAuth API
import { API_ENDPOINTS } from './config'

// 從後端獲取 Twitch OAuth URL
export async function getTwitchOAuthUrl(): Promise<string> {
  const response = await fetch(API_ENDPOINTS.auth.twitchOAuth)
  if (!response.ok) {
    throw new Error('Failed to fetch OAuth URL')
  }
  const data = await response.json()
  return data.oauth_url
}

// 開啟 Twitch OAuth 登入 - 直接跳轉當前頁面
export async function openTwitchOAuth(): Promise<void> {
  try {
    const oauthUrl = await getTwitchOAuthUrl()
    window.location.href = oauthUrl
  } catch (error) {
    console.error('Failed to open OAuth:', error)
    throw error
  }
}
