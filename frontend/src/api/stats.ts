// Stats API

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
    const response = await fetch('/api/stats/channel', {
      credentials: 'include',
    })

    if (!response.ok) {
      console.error(`Failed to fetch stats: ${response.status} ${response.statusText}`)
      const errorText = await response.text().catch(() => 'No error details')
      console.error('Error details:', errorText)
      return null
    }

    const data = await response.json()
    console.log('Stats data received:', data)
    return data
  } catch (error) {
    console.error('Failed to get channel stats:', error)
    return null
  }
}
