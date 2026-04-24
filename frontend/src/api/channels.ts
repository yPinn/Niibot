import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'

export interface Channel {
  id: string
  name: string
  display_name: string
  avatar: string
  is_live: boolean
  viewer_count?: number
  game_name?: string
  title?: string
}

export interface ChannelStatus {
  subscribed: boolean
  channel_id: string
  channel_name: string
}

export interface ToggleChannelRequest {
  channel_id: string
  enabled: boolean
}

export interface ToggleChannelResponse {
  message: string
}

async function fetchTwitchMonitoredChannels(): Promise<Channel[]> {
  try {
    const response = await apiFetch(API_ENDPOINTS.channels.twitch.monitored, {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error('Failed to fetch channels')
    }
    return await response.json()
  } catch (error) {
    if (import.meta.env.DEV) console.error('Failed to get channels:', error)
    return []
  }
}

export async function getTwitchMonitoredChannels(options?: {
  forceRefresh?: boolean
}): Promise<Channel[]> {
  return apiCache.fetch(CACHE_KEYS.CHANNELS, fetchTwitchMonitoredChannels, {
    ttl: 10 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}

export async function getTwitchChannelStatus(): Promise<ChannelStatus | null> {
  try {
    const response = await apiFetch(API_ENDPOINTS.channels.twitch.myStatus, {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error('Failed to fetch channel status')
    }
    return response.json()
  } catch (error) {
    if (import.meta.env.DEV) console.error('Failed to get channel status:', error)
    return null
  }
}

// ---- Channel Defaults (cooldown settings) ----

export interface ChannelDefaults {
  default_cooldown: number
}

export async function getChannelDefaults(): Promise<ChannelDefaults> {
  const response = await apiFetch(API_ENDPOINTS.channels.defaults, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to fetch channel defaults')
  return response.json()
}

export async function updateChannelDefaults(
  data: Partial<ChannelDefaults>
): Promise<ChannelDefaults> {
  const response = await apiFetch(API_ENDPOINTS.channels.defaults, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error('Failed to update channel defaults')
  return response.json()
}

// ---- Bot Mod Status ----

export interface ModStatusResponse {
  is_moderator: boolean
}

export interface GrantModResponse {
  granted: boolean
  already_mod: boolean
}

export async function getBotModStatus(): Promise<ModStatusResponse | null> {
  try {
    const response = await apiFetch(API_ENDPOINTS.channels.twitch.modStatus, {
      credentials: 'include',
    })
    if (!response.ok) return null
    return response.json()
  } catch {
    return null
  }
}

export async function grantBotMod(): Promise<GrantModResponse> {
  const response = await apiFetch(API_ENDPOINTS.channels.twitch.grantMod, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to grant moderator status')
  return response.json()
}

export async function toggleTwitchChannel(
  channelId: string,
  enabled: boolean
): Promise<ToggleChannelResponse> {
  const response = await apiFetch(API_ENDPOINTS.channels.twitch.toggle, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    credentials: 'include',
    body: JSON.stringify({
      channel_id: channelId,
      enabled,
    }),
  })

  if (!response.ok) {
    throw new Error('Failed to toggle channel')
  }

  return response.json()
}
