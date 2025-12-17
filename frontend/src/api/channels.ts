// Channels API
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

// 內部函數：實際的 API 調用
async function fetchMonitoredChannels(): Promise<Channel[]> {
  try {
    const response = await fetch(API_ENDPOINTS.channels.list, {
      credentials: 'include', // 包含 cookies
    })
    if (!response.ok) {
      throw new Error('Failed to fetch channels')
    }
    const data = await response.json()
    return data
  } catch (error) {
    console.error('Failed to get channels:', error)
    return []
  }
}

// 獲取監聽的頻道列表（帶快取）
export async function getMonitoredChannels(options?: {
  forceRefresh?: boolean
}): Promise<Channel[]> {
  return apiCache.fetch(CACHE_KEYS.CHANNELS, fetchMonitoredChannels, {
    ttl: 2 * 60 * 1000, // 2 分鐘（頻道狀態可能更頻繁變化）
    forceRefresh: options?.forceRefresh,
  })
}
