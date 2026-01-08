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
  channel_id: string
  bot_enabled: boolean
}

export interface ToggleChannelRequest {
  channel_id: string
  enabled: boolean
}

export interface ToggleChannelResponse {
  message: string
}

async function fetchMonitoredChannels(): Promise<Channel[]> {
  try {
    const response = await fetch(API_ENDPOINTS.channels.monitored, {
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

export async function getMonitoredChannels(options?: {
  forceRefresh?: boolean
}): Promise<Channel[]> {
  return apiCache.fetch(CACHE_KEYS.CHANNELS, fetchMonitoredChannels, {
    ttl: 2 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}

export async function getMyChannelStatus(): Promise<ChannelStatus | null> {
  try {
    const response = await fetch(API_ENDPOINTS.channels.myStatus, {
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

export async function toggleChannel(
  channelId: string,
  enabled: boolean
): Promise<ToggleChannelResponse> {
  const response = await fetch(API_ENDPOINTS.channels.toggle, {
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
