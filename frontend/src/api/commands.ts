import { API_ENDPOINTS } from './config'

export interface CommandConfig {
  id: number
  channel_id: string
  command_name: string
  command_type: 'builtin' | 'custom'
  enabled: boolean
  custom_response: string | null
  redirect_to: string | null
  cooldown_global: number
  cooldown_per_user: number
  min_role: string
  aliases: string | null
  usage_count: number
}

export interface CommandConfigUpdate {
  enabled?: boolean
  custom_response?: string | null
  redirect_to?: string | null
  cooldown_global?: number
  cooldown_per_user?: number
  min_role?: string
  aliases?: string | null
}

export interface CustomCommandCreate {
  command_name: string
  custom_response?: string | null
  redirect_to?: string | null
  cooldown_global?: number
  cooldown_per_user?: number
  min_role?: string
  aliases?: string | null
}

export interface RedemptionConfig {
  id: number
  channel_id: string
  action_type: string
  reward_name: string
  enabled: boolean
}

export interface RedemptionConfigUpdate {
  reward_name: string
  enabled: boolean
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

// ---- Redemption Configs ----

export async function getRedemptionConfigs(): Promise<RedemptionConfig[]> {
  const response = await fetch(API_ENDPOINTS.commands.redemptions, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch redemption configs: ${response.statusText}`)
  return response.json()
}

export async function updateRedemptionConfig(
  actionType: string,
  data: RedemptionConfigUpdate
): Promise<RedemptionConfig> {
  const response = await fetch(API_ENDPOINTS.commands.updateRedemption(actionType), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update redemption config: ${response.statusText}`)
  return response.json()
}
