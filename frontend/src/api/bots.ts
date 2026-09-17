import { API_ENDPOINTS, apiFetch } from './config'

/** DB connection-pool gauge — same shape from every service's /status. */
export interface DbPoolGauge {
  size: number
  idle: number
  min_size: number
  max_size: number
}

/** One in-process AsyncTTLCache's occupancy — keyed by cache name in `caches`. */
export interface CacheGauge {
  size: number
  stale: number
  maxsize: number
}

export interface AIProviderStatus {
  provider: 'groq' | 'gemini' | 'openrouter'
  state: 'ready' | 'disabled' | 'misconfigured'
  model?: string | null
  reason?: string | null
}

export interface AICircuitStatus {
  provider: string
  model: string
  state: 'closed' | 'open' | 'half_open' | 'unhealthy'
  consecutive_failures: number
}

export interface AIMemoryStatus {
  active_sessions: number
  total_chars: number
  ttl_evictions: number
  lru_evictions: number
  budget_evictions: number
  oversized_turn_rejections: number
}

export interface AIRuntimeStatus {
  providers: AIProviderStatus[]
  circuits: AICircuitStatus[]
  memory?: AIMemoryStatus
}

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
  // AI
  ai_model?: string
  ai_status?: AIRuntimeStatus | null
  // Runtime gauges (twitch only — memory is per-channel in-process state, has
  // no API-side equivalent)
  db_pool?: DbPoolGauge
  caches?: Record<string, CacheGauge>
  memory?: Record<string, number>
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
  db_pool?: DbPoolGauge
  caches?: Record<string, CacheGauge>
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
    db_pool: data.db_pool,
    caches: data.caches,
  }
}
