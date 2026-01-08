// API 端點配置集中管理
export const API_BASE_URL = import.meta.env.VITE_API_URL || ''
export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: '/api/auth/twitch/oauth',
    twitchCallback: '/api/auth/twitch/callback',
    user: '/api/auth/user',
    logout: '/api/auth/logout',
  },
  channels: {
    monitored: '/api/channels/monitored',
    myStatus: '/api/channels/my-status',
    toggle: '/api/channels/toggle',
  },
  analytics: {
    summary: '/api/analytics/summary',
    topCommands: '/api/analytics/top-commands',
    sessionCommands: (sessionId: number) => `/api/analytics/sessions/${sessionId}/commands`,
    sessionEvents: (sessionId: number) => `/api/analytics/sessions/${sessionId}/events`,
  },
  stats: {
    channel: '/api/stats/channel',
  },
  commands: {
    components: '/api/commands/components',
  },
  health: '/api/health',
} as const
