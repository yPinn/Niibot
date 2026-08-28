import { apiCache, CACHE_KEYS } from '@/lib/apiCache'
import { reportSilent } from '@/lib/clientErrorReporter'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

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

export async function getChannelStats(days = 30): Promise<ChannelStats | null> {
  return apiCache.fetch(
    CACHE_KEYS.STATS_CHANNEL(days),
    async () => {
      try {
        const response = await apiFetch(`${API_ENDPOINTS.stats.channel}?days=${days}`, {
          credentials: 'include',
        })
        if (!response.ok) {
          reportSilent(await parseApiError(response, '載入頻道統計失敗'))
          return null
        }
        return (await response.json()) as ChannelStats
      } catch (error) {
        if (import.meta.env.DEV) console.error('Failed to get channel stats:', error)
        reportSilent(error)
        return null
      }
    },
    { ttl: 5 * 60 * 1000 }
  )
}
