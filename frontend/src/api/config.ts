// API 端點配置

const getBaseUrl = (): string => {
  // 1. 取得環境變數
  const rawBase = import.meta.env.VITE_API_URL || ''
  if (!rawBase) return ''

  // 2. 自動補齊 https:// 並移除結尾斜線
  const withProtocol = rawBase.startsWith('http') ? rawBase : `https://${rawBase}`
  return withProtocol.replace(/\/$/, '')
}

export const API_BASE_URL = getBaseUrl()

// 3. 核心工具：強制拼接 Base URL，避免請求發往前端網域
const join = (path: string) => `${API_BASE_URL}${path}`

export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: join('/api/auth/twitch/oauth'),
    twitchCallback: join('/api/auth/twitch/callback'),
    discordStatus: join('/api/auth/discord/status'),
    discordOAuth: join('/api/auth/discord/oauth'),
    discordCallback: join('/api/auth/discord/callback'),
    user: join('/api/auth/user'),
    logout: join('/api/auth/logout'),
  },
  channels: {
    twitch: {
      monitored: join('/api/channels/twitch/monitored'),
      myStatus: join('/api/channels/twitch/my-status'),
      toggle: join('/api/channels/twitch/toggle'),
    },
  },
  analytics: {
    summary: join('/api/analytics/summary'),
    topCommands: join('/api/analytics/top-commands'),
    sessionCommands: (session_id: number) => join(`/api/analytics/sessions/${session_id}/commands`),
    sessionEvents: (session_id: number) => join(`/api/analytics/sessions/${session_id}/events`),
  },
  stats: {
    channel: join('/api/stats/channel'),
  },
  commands: {
    components: join('/api/commands/components'),
  },
  bots: {
    twitch: {
      status: join('/api/bots/twitch/status'),
      health: join('/api/bots/twitch/health'),
    },
    discord: {
      status: join('/api/bots/discord/status'),
      health: join('/api/bots/discord/health'),
    },
  },
  health: join('/health'),
} as const
