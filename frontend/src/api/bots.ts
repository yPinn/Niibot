import { API_ENDPOINTS, apiFetch } from './config'

export interface BotStatus {
  online: boolean
  service?: string
  version?: string
  git_commit?: string
  started_at?: string
  bot_id?: string
  uptime_seconds?: number
  ready?: boolean
  // Twitch
  connected_channels?: number
  components?: number
  // Discord
  guilds?: number
  cogs?: number
  ws_latency_ms?: number
}

export interface ApiServerStatus {
  online: boolean
  service?: string
  version?: string
  git_commit?: string
  started_at?: string
  uptime_seconds?: number
  db_connected?: boolean
  environment?: string
}

export async function getTwitchBotStatus(): Promise<BotStatus> {
  const response = await apiFetch(API_ENDPOINTS.bots.twitch.status, { credentials: 'include' })
  if (!response.ok) return { online: false }
  return response.json()
}

export async function getDiscordBotStatus(): Promise<BotStatus> {
  const response = await apiFetch(API_ENDPOINTS.bots.discord.status, { credentials: 'include' })
  if (!response.ok) return { online: false }
  return response.json()
}

export async function getApiServerStatus(): Promise<ApiServerStatus> {
  const response = await apiFetch(API_ENDPOINTS.status, { credentials: 'include' })
  if (!response.ok) return { online: false }
  const data = await response.json()
  return {
    online: true,
    service: data.service,
    version: data.version,
    git_commit: data.git_commit,
    started_at: data.started_at,
    uptime_seconds: data.uptime_seconds,
    db_connected: data.db_connected,
    environment: data.environment,
  }
}
