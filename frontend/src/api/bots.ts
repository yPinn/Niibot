import { API_ENDPOINTS } from './config'

export interface BotStatus {
  online: boolean
  service?: string
  bot_id?: string
  uptime_seconds?: number
  connected_channels?: number
}

export async function getTwitchBotStatus(): Promise<BotStatus> {
  const response = await fetch(API_ENDPOINTS.bots.twitch.status, {
    credentials: 'include',
  })

  if (!response.ok) {
    return { online: false }
  }

  return response.json()
}

export async function getDiscordBotStatus(): Promise<BotStatus> {
  const response = await fetch(API_ENDPOINTS.bots.discord.status, {
    credentials: 'include',
  })

  if (!response.ok) {
    return { online: false }
  }

  return response.json()
}
