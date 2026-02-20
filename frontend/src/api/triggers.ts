import { API_ENDPOINTS } from './config'

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
}

export async function getTriggerConfigs(): Promise<TriggerConfig[]> {
  const response = await fetch(API_ENDPOINTS.triggers.configs, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch triggers: ${response.statusText}`)
  return response.json()
}

export async function createTrigger(data: TriggerCreate): Promise<TriggerConfig> {
  const response = await fetch(API_ENDPOINTS.triggers.createConfig, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail ?? `Failed to create trigger: ${response.statusText}`)
  }
  return response.json()
}

export async function updateTrigger(name: string, data: TriggerUpdate): Promise<TriggerConfig> {
  const response = await fetch(API_ENDPOINTS.triggers.updateConfig(name), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail ?? `Failed to update trigger: ${response.statusText}`)
  }
  return response.json()
}

export async function toggleTrigger(name: string, enabled: boolean): Promise<TriggerConfig> {
  const response = await fetch(API_ENDPOINTS.triggers.toggleConfig(name), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) throw new Error(`Failed to toggle trigger: ${response.statusText}`)
  return response.json()
}

export async function deleteTrigger(name: string): Promise<void> {
  const response = await fetch(API_ENDPOINTS.triggers.deleteConfig(name), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to delete trigger: ${response.statusText}`)
}
