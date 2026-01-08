import { API_ENDPOINTS } from './config'

export interface CommandStat {
  name: string
  count: number
}

export interface ChatterStat {
  username: string
  message_count: number
}

export interface ChannelStats {
  top_commands: CommandStat[]
  top_chatters: ChatterStat[]
  total_messages: number
  total_commands: number
}

export async function getChannelStats(): Promise<ChannelStats | null> {
  try {
    const response = await fetch(API_ENDPOINTS.stats.channel, {
      credentials: 'include',
    })

    if (!response.ok) {
      console.error(`Failed to fetch stats: ${response.status} ${response.statusText}`)
      return null
    }

    return await response.json()
  } catch (error) {
    console.error('Failed to get channel stats:', error)
    return null
  }
}
