import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS } from './config'

export interface Channel {
  id: string
  name: string
  display_name: string
  avatar: string
  is_live: boolean
  viewer_count?: number
  game_name?: string
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
    const response = await fetch(API_ENDPOINTS.channels.twitch.monitored, {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error('Failed to fetch channels')
    }
    return await response.json()
  } catch (error) {
    console.error('Failed to get channels:', error)
    return []
  }
}

export async function getTwitchMonitoredChannels(options?: {
  forceRefresh?: boolean
}): Promise<Channel[]> {
  return apiCache.fetch(CACHE_KEYS.CHANNELS, fetchTwitchMonitoredChannels, {
    ttl: 2 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}

export async function getTwitchChannelStatus(): Promise<ChannelStatus | null> {
  try {
    const response = await fetch(API_ENDPOINTS.channels.twitch.myStatus, {
      credentials: 'include',
    })
    if (!response.ok) {
      throw new Error('Failed to fetch channel status')
    }
    return response.json()
  } catch (error) {
    console.error('Failed to get channel status:', error)
    return null
  }
}

export async function toggleTwitchChannel(
  channelId: string,
  enabled: boolean
): Promise<ToggleChannelResponse> {
  const response = await fetch(API_ENDPOINTS.channels.twitch.toggle, {
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
