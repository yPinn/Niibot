import { API_ENDPOINTS } from './config'

export interface BotStatus {
  online: boolean
  service?: string
  bot_id?: string
  uptime_seconds?: number
  connected_channels?: number
}

export interface ApiServerStatus {
  online: boolean
  service?: string
  uptime_seconds?: number
  db_connected?: boolean
}

// ---------------------------------------------------------------------------
// Dedup cache — 防止同一時間窗口內重複發送相同請求
// 主要 polling 由 ServiceStatusContext 統一控制，此處為安全網
// ---------------------------------------------------------------------------
const CACHE_TTL = 10_000 // 10s

const cache = new Map<string, { data: unknown; ts: number }>()

async function cachedFetch<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const entry = cache.get(key)
  if (entry && Date.now() - entry.ts < CACHE_TTL) {
    return entry.data as T
  }
  const data = await fetcher()
  cache.set(key, { data, ts: Date.now() })
  return data
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function getTwitchBotStatus(): Promise<BotStatus> {
  return cachedFetch('twitch', async () => {
    const response = await fetch(API_ENDPOINTS.bots.twitch.status, {
      credentials: 'include',
    })
    if (!response.ok) return { online: false }
    return response.json()
  })
}

export async function getDiscordBotStatus(): Promise<BotStatus> {
  return cachedFetch('discord', async () => {
    const response = await fetch(API_ENDPOINTS.bots.discord.status, {
      credentials: 'include',
    })
    if (!response.ok) return { online: false }
    return response.json()
  })
}

export async function getApiServerStatus(): Promise<ApiServerStatus> {
  return cachedFetch('api', async () => {
    const response = await fetch(API_ENDPOINTS.status, {
      credentials: 'include',
    })
    if (!response.ok) return { online: false }
    const data = await response.json()
    return {
      online: true,
      service: data.service,
      uptime_seconds: data.uptime_seconds,
      db_connected: data.db_connected,
    }
  })
}
