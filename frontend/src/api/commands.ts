import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface CommandConfig {
  /** Null for builtin commands without an explicit DB row. */
  id: number | null
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
  detail: string
  usage: string
  preview_input: string
  preview_output: string
  audience: 'viewer' | 'broadcaster' | 'moderator' | null
  public_visible: boolean
  display_order: number
  /** Display label for the builtin's category; null for custom commands. */
  category_label: string | null
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

export function getCommandConfigs(): Promise<CommandConfig[]> {
  return apiJson(
    API_ENDPOINTS.commands.configs,
    { credentials: 'include' },
    { fallback: '載入指令設定失敗' }
  )
}

export function createCustomCommand(data: CustomCommandCreate): Promise<CommandConfig> {
  return apiJson(
    API_ENDPOINTS.commands.createConfig,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '建立自訂指令失敗' }
  )
}

export function updateCommandConfig(
  commandName: string,
  data: CommandConfigUpdate
): Promise<CommandConfig> {
  return apiJson(
    API_ENDPOINTS.commands.updateConfig(commandName),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新指令設定失敗' }
  )
}

export function toggleCommandConfig(commandName: string, enabled: boolean): Promise<CommandConfig> {
  return apiJson(
    API_ENDPOINTS.commands.toggleConfig(commandName),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    },
    { fallback: '切換指令設定失敗' }
  )
}

export function deleteCustomCommand(commandName: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.commands.deleteConfig(commandName),
    { method: 'DELETE', credentials: 'include' },
    { fallback: '刪除自訂指令失敗' }
  )
}

// ---- Public Commands ----

export interface PublicCommand {
  name: string
  description: string
  min_role: string
  command_type: 'builtin' | 'custom' | 'trigger'
  /** Display label for the builtin's category. Null for custom commands; absent for triggers. */
  category_label?: string | null
}

export interface PublicChannelProfile {
  display_name: string | null
  profile_image_url: string | null
}

export interface PublicCommandsData {
  channel: PublicChannelProfile
  commands: PublicCommand[]
}

export function getPublicCommands(username: string): Promise<PublicCommandsData> {
  return apiJson(API_ENDPOINTS.commands.public(username), undefined, {
    fallback: '載入公開指令失敗',
  })
}
