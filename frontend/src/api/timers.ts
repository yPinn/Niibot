import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface TimerConfig {
  id: number | null
  channel_id: string
  timer_name: string
  interval_seconds: number
  min_lines: number
  message_template: string
  enabled: boolean
  announce: boolean
  command_alias: string | null
  builtin?: boolean
  created_at: string | null
  updated_at: string | null
}

export interface TimerCreate {
  timer_name: string
  interval_seconds: number
  min_lines?: number
  message_template: string
  announce?: boolean
  command_alias?: string | null
}

export interface TimerUpdate {
  interval_seconds?: number
  min_lines?: number
  message_template?: string
  enabled?: boolean
  announce?: boolean
  command_alias?: string | null
  clear_alias?: boolean
}

export function getTimerConfigs(): Promise<TimerConfig[]> {
  return apiJson(
    API_ENDPOINTS.timers.configs,
    { credentials: 'include' },
    { fallback: '載入計時器失敗' }
  )
}

export function createTimer(data: TimerCreate): Promise<TimerConfig> {
  return apiJson(
    API_ENDPOINTS.timers.createConfig,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '建立計時器失敗' }
  )
}

export function updateTimer(name: string, data: TimerUpdate): Promise<TimerConfig> {
  return apiJson(
    API_ENDPOINTS.timers.updateConfig(name),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新計時器失敗' }
  )
}

export function toggleTimer(name: string, enabled: boolean): Promise<TimerConfig> {
  return apiJson(
    API_ENDPOINTS.timers.toggleConfig(name),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    },
    { fallback: '切換計時器失敗' }
  )
}

export function deleteTimer(name: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.timers.deleteConfig(name),
    { method: 'DELETE', credentials: 'include' },
    { fallback: '刪除計時器失敗' }
  )
}
