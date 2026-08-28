import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface TriggerConfig {
  id: number
  channel_id: string
  trigger_name: string
  match_type: 'contains' | 'startswith' | 'exact' | 'regex'
  pattern: string
  case_sensitive: boolean
  response: string
  min_role: string
  cooldown: number | null
  priority: number
  enabled: boolean
  usage_count: number
  aliases: string | null
  created_at: string | null
  updated_at: string | null
}

export interface TriggerCreate {
  trigger_name: string
  match_type?: 'contains' | 'startswith' | 'exact' | 'regex'
  pattern: string
  case_sensitive?: boolean
  response: string
  min_role?: string
  cooldown?: number | null
  priority?: number
  aliases?: string | null
}

export interface TriggerUpdate {
  match_type?: 'contains' | 'startswith' | 'exact' | 'regex'
  pattern?: string
  case_sensitive?: boolean
  response?: string
  min_role?: string
  cooldown?: number | null
  priority?: number
  enabled?: boolean
  aliases?: string | null
}

export function getTriggerConfigs(): Promise<TriggerConfig[]> {
  return apiJson(
    API_ENDPOINTS.triggers.configs,
    { credentials: 'include' },
    { fallback: '載入觸發詞失敗' }
  )
}

export function createTrigger(data: TriggerCreate): Promise<TriggerConfig> {
  return apiJson(
    API_ENDPOINTS.triggers.createConfig,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '建立觸發詞失敗' }
  )
}

export function updateTrigger(name: string, data: TriggerUpdate): Promise<TriggerConfig> {
  return apiJson(
    API_ENDPOINTS.triggers.updateConfig(name),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新觸發詞失敗' }
  )
}

export function toggleTrigger(name: string, enabled: boolean): Promise<TriggerConfig> {
  return apiJson(
    API_ENDPOINTS.triggers.toggleConfig(name),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    },
    { fallback: '切換觸發詞失敗' }
  )
}

export function deleteTrigger(name: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.triggers.deleteConfig(name),
    { method: 'DELETE', credentials: 'include' },
    { fallback: '刪除觸發詞失敗' }
  )
}
