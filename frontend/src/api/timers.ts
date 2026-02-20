import { API_ENDPOINTS } from './config'

export interface TimerConfig {
  id: number
  channel_id: string
  timer_name: string
  interval_seconds: number
  min_lines: number
  message_template: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface TimerCreate {
  timer_name: string
  interval_seconds: number
  min_lines?: number
  message_template: string
}

export interface TimerUpdate {
  interval_seconds?: number
  min_lines?: number
  message_template?: string
  enabled?: boolean
}

export async function getTimerConfigs(): Promise<TimerConfig[]> {
  const response = await fetch(API_ENDPOINTS.timers.configs, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch timers: ${response.statusText}`)
  return response.json()
}

export async function createTimer(data: TimerCreate): Promise<TimerConfig> {
  const response = await fetch(API_ENDPOINTS.timers.createConfig, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail ?? `Failed to create timer: ${response.statusText}`)
  }
  return response.json()
}

export async function updateTimer(name: string, data: TimerUpdate): Promise<TimerConfig> {
  const response = await fetch(API_ENDPOINTS.timers.updateConfig(name), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({}))
    throw new Error(err.detail ?? `Failed to update timer: ${response.statusText}`)
  }
  return response.json()
}

export async function toggleTimer(name: string, enabled: boolean): Promise<TimerConfig> {
  const response = await fetch(API_ENDPOINTS.timers.toggleConfig(name), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) throw new Error(`Failed to toggle timer: ${response.statusText}`)
  return response.json()
}

export async function deleteTimer(name: string): Promise<void> {
  const response = await fetch(API_ENDPOINTS.timers.deleteConfig(name), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to delete timer: ${response.statusText}`)
}
