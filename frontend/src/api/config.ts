// API endpoint configuration
export const API_BASE_URL = import.meta.env.VITE_API_URL || ''
export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: '/api/auth/twitch/oauth',
    twitchCallback: '/api/auth/twitch/callback',
    discordStatus: '/api/auth/discord/status',
    discordOAuth: '/api/auth/discord/oauth',
    discordCallback: '/api/auth/discord/callback',
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
    sessionCommands: (session_id: number) => `/api/analytics/sessions/${session_id}/commands`,
    sessionEvents: (session_id: number) => `/api/analytics/sessions/${session_id}/events`,
  },
  stats: {
    channel: '/api/stats/channel',
  },
  commands: {
    components: '/api/commands/components',
  },
  bots: {
    twitch: {
      status: '/api/bots/twitch/status',
      health: '/api/bots/twitch/health',
    },
    discord: {
      status: '/api/bots/discord/status',
      health: '/api/bots/discord/health',
    },
  },
  health: '/api/health',
} as const
