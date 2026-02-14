import { API_ENDPOINTS } from './config'

export interface EventConfig {
  id: number
  channel_id: string
  event_type: 'follow' | 'subscribe' | 'raid'
  message_template: string
  enabled: boolean
  options: Record<string, unknown>
  trigger_count: number
}

export interface EventConfigUpdate {
  message_template: string
  enabled: boolean
  options?: Record<string, unknown>
}

export interface TwitchReward {
  id: string
  title: string
  cost: number
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

// ---- Twitch Rewards ----

export async function getTwitchRewards(): Promise<TwitchReward[]> {
  const response = await fetch(API_ENDPOINTS.events.twitchRewards, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch Twitch rewards: ${response.statusText}`)
  return response.json()
}

// ---- Redemption Configs ----

export async function getRedemptionConfigs(): Promise<RedemptionConfig[]> {
  const response = await fetch(API_ENDPOINTS.events.redemptions, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch redemption configs: ${response.statusText}`)
  return response.json()
}

export async function updateRedemptionConfig(
  actionType: string,
  data: RedemptionConfigUpdate
): Promise<RedemptionConfig> {
  const response = await fetch(API_ENDPOINTS.events.updateRedemption(actionType), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update redemption config: ${response.statusText}`)
  return response.json()
}
