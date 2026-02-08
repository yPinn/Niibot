import { API_ENDPOINTS } from './config'

export interface EventConfig {
  id: number
  channel_id: string
  event_type: 'follow' | 'subscribe' | 'raid'
  message_template: string
  enabled: boolean
  trigger_count: number
}

export interface EventConfigUpdate {
  message_template: string
  enabled: boolean
}

export async function getEventConfigs(): Promise<EventConfig[]> {
  const response = await fetch(API_ENDPOINTS.events.configs, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch event configs: ${response.statusText}`)
  return response.json()
}

export async function updateEventConfig(
  eventType: string,
  data: EventConfigUpdate
): Promise<EventConfig> {
  const response = await fetch(API_ENDPOINTS.events.updateConfig(eventType), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update event config: ${response.statusText}`)
  return response.json()
}

export async function toggleEventConfig(eventType: string, enabled: boolean): Promise<EventConfig> {
  const response = await fetch(API_ENDPOINTS.events.toggleConfig(eventType), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) throw new Error(`Failed to toggle event config: ${response.statusText}`)
  return response.json()
}
