import { API_BASE_URL } from './config'

export interface CommandInfo {
  name: string
  aliases: string[]
  description: string | null
  platform: 'discord' | 'twitch'
}

export interface ComponentInfo {
  name: string
  description: string | null
  file_path: string
  platform: 'discord' | 'twitch'
  commands: CommandInfo[]
}

export interface ComponentsResponse {
  discord: ComponentInfo[]
  twitch: ComponentInfo[]
  total: number
}

/**
 * Get all bot components (Discord cogs and Twitch components)
 */
export async function getComponents(): Promise<ComponentsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/commands/components`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error('Failed to fetch components')
  }

  return response.json()
}
