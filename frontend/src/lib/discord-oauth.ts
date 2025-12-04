// Discord OAuth 配置
const DISCORD_CLIENT_ID = import.meta.env.VITE_DISCORD_CLIENT_ID
const DISCORD_REDIRECT_URI = import.meta.env.VITE_DISCORD_REDIRECT_URI
const DISCORD_OAUTH_URL = 'https://discord.com/api/oauth2/authorize'

// 生成 Discord OAuth 登入 URL
export function getDiscordAuthUrl(): string {
  const params = new URLSearchParams({
    client_id: DISCORD_CLIENT_ID,
    redirect_uri: DISCORD_REDIRECT_URI,
    response_type: 'code',
    scope: 'identify email',
  })

  return `${DISCORD_OAUTH_URL}?${params.toString()}`
}

// Discord 用戶資料類型
export interface DiscordUser {
  id: string
  username: string
  discriminator: string
  avatar: string | null
  email?: string
}

// 處理 OAuth 回調（前端部分）
export function handleDiscordCallback() {
  const urlParams = new URLSearchParams(window.location.search)
  const code = urlParams.get('code')
  const error = urlParams.get('error')

  if (error) {
    console.error('Discord OAuth error:', error)
    return { success: false, error }
  }

  if (code) {
    // 這裡需要將 code 發送到後端進行驗證
    return { success: true, code }
  }

  return { success: false, error: 'No code received' }
}
