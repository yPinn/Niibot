// Channels API
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

// 獲取監聽的頻道列表
export async function getMonitoredChannels(): Promise<Channel[]> {
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
