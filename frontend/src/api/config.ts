// API Configuration

// API base URL (開發環境使用 Vite proxy)
export const API_BASE_URL = import.meta.env.VITE_API_URL || ''

// API endpoints
export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: '/api/auth/twitch/oauth',
    user: '/api/auth/user',
    logout: '/api/auth/logout',
  },
} as const
