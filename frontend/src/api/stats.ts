import { API_ENDPOINTS, apiFetch } from './config'

export interface CommandStat {
  name: string
  count: number
}

export interface ChatterStat {
  username: string
  display_name?: string | null
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
    const response = await apiFetch(API_ENDPOINTS.stats.channel, {
      credentials: 'include',
    })

    if (!response.ok) {
      if (import.meta.env.DEV)
        console.error(`Failed to fetch stats: ${response.status} ${response.statusText}`)
      return null
    }

    return await response.json()
  } catch (error) {
    if (import.meta.env.DEV) console.error('Failed to get channel stats:', error)
    return null
  }
}
