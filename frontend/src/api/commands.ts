import { API_ENDPOINTS } from './config'

export interface CommandConfig {
  id: number
  channel_id: string
  command_name: string
  command_type: 'builtin' | 'custom'
  enabled: boolean
  custom_response: string | null
  cooldown: number | null
  min_role: string
  aliases: string | null
  usage_count: number
  description: string
}

export interface CommandConfigUpdate {
  enabled?: boolean
  custom_response?: string | null
  cooldown?: number | null
  min_role?: string
  aliases?: string | null
}

export interface CustomCommandCreate {
  command_name: string
  custom_response?: string | null
  cooldown?: number | null
  min_role?: string
  aliases?: string | null
}

// ---- Command Configs ----

export async function getCommandConfigs(): Promise<CommandConfig[]> {
  const response = await fetch(API_ENDPOINTS.commands.configs, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch command configs: ${response.statusText}`)
  return response.json()
}

export async function createCustomCommand(data: CustomCommandCreate): Promise<CommandConfig> {
  const response = await fetch(API_ENDPOINTS.commands.createConfig, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to create custom command: ${response.statusText}`)
  return response.json()
}

export async function updateCommandConfig(
  commandName: string,
  data: CommandConfigUpdate
): Promise<CommandConfig> {
  const response = await fetch(API_ENDPOINTS.commands.updateConfig(commandName), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update command config: ${response.statusText}`)
  return response.json()
}

export async function toggleCommandConfig(
  commandName: string,
  enabled: boolean
): Promise<CommandConfig> {
  const response = await fetch(API_ENDPOINTS.commands.toggleConfig(commandName), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) throw new Error(`Failed to toggle command config: ${response.statusText}`)
  return response.json()
}

export async function deleteCustomCommand(commandName: string): Promise<void> {
  const response = await fetch(API_ENDPOINTS.commands.deleteConfig(commandName), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to delete custom command: ${response.statusText}`)
}

// ---- Public Commands ----

export interface PublicCommand {
  name: string
  description: string
  min_role: string
  command_type: 'builtin' | 'custom' | 'trigger'
}

export interface PublicChannelProfile {
  display_name: string | null
  profile_image_url: string | null
}

export interface PublicCommandsData {
  channel: PublicChannelProfile
  commands: PublicCommand[]
}

export async function getPublicCommands(username: string): Promise<PublicCommandsData> {
  const response = await fetch(API_ENDPOINTS.commands.public(username))
  if (!response.ok) throw new Error(`Failed to fetch public commands: ${response.statusText}`)
  return response.json()
}
