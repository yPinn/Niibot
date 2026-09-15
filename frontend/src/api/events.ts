import { API_ENDPOINTS, apiFetch } from './config'
import { apiJson } from './errors'

export interface EventConfig {
  id: number
  channel_id: string
  event_type: 'follow' | 'subscribe' | 'resub' | 'gift_sub' | 'gift_recipient' | 'raid' | 'bits'
  message_template: string
  enabled: boolean
  options: Record<string, unknown>
  // null when the event writes no stream_events row (resub / gift_sub)
  trigger_count: number | null
}

export interface EventVariable {
  name: string
  description: string
  sample: string
}

export interface EventOption {
  key: string
  type: 'boolean'
  label: string
  description: string
  default: boolean
}

export interface EventDefinition {
  key: string
  display_name: string
  category_label: string
  accent: string
  requires_affiliate: boolean
  default_template: string
  default_enabled: boolean
  variables: EventVariable[]
  options_schema: EventOption[]
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
  is_enabled: boolean
  is_paused: boolean
  is_in_stock: boolean
  should_redemptions_skip_request_queue: boolean
  max_per_stream: number | null
  max_per_user_per_stream: number | null
}

export interface RedemptionConfig {
  id: number
  channel_id: string
  action_type: string
  reward_name: string
  reward_id: string | null
  enabled: boolean
  first_message: string
  first_announce_color: string
}

export interface RedemptionConfigUpdate {
  reward_name: string
  reward_id?: string | null
  enabled: boolean
}

export interface FirstSettingsUpdate {
  message: string
  announce_color: string
}

export function getEventCatalog(): Promise<EventDefinition[]> {
  return apiJson(
    API_ENDPOINTS.events.catalog,
    { credentials: 'include' },
    { fallback: '載入事件目錄失敗' }
  )
}

export function getEventConfigs(): Promise<EventConfig[]> {
  return apiJson(
    API_ENDPOINTS.events.configs,
    { credentials: 'include' },
    { fallback: '載入事件設定失敗' }
  )
}

export function updateEventConfig(
  eventType: string,
  data: EventConfigUpdate
): Promise<EventConfig> {
  return apiJson(
    API_ENDPOINTS.events.updateConfig(eventType),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新事件設定失敗' }
  )
}

export function toggleEventConfig(eventType: string, enabled: boolean): Promise<EventConfig> {
  return apiJson(
    API_ENDPOINTS.events.toggleConfig(eventType),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ enabled }),
    },
    { fallback: '切換事件設定失敗' }
  )
}

// ---- Twitch Rewards ----

export class NonPartnerError extends Error {
  constructor() {
    super('Channel is not an affiliate or partner')
    this.name = 'NonPartnerError'
  }
}

export async function getTwitchRewards(): Promise<TwitchReward[]> {
  // 403 here means "not affiliate/partner", a normal state — not an error toast.
  const response = await apiFetch(API_ENDPOINTS.events.twitchRewards, {
    credentials: 'include',
  })
  if (response.status === 403) throw new NonPartnerError()
  if (!response.ok) throw new Error(`Failed to fetch Twitch rewards: ${response.statusText}`)
  return response.json()
}

// ---- Redemption Configs ----

export function getRedemptionConfigs(): Promise<RedemptionConfig[]> {
  return apiJson(
    API_ENDPOINTS.events.redemptions,
    { credentials: 'include' },
    { fallback: '載入兌換設定失敗' }
  )
}

export function updateRedemptionConfig(
  actionType: string,
  data: RedemptionConfigUpdate
): Promise<RedemptionConfig> {
  return apiJson(
    API_ENDPOINTS.events.updateRedemption(actionType),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新兌換設定失敗' }
  )
}

export function updateFirstRedemptionSettings(
  data: FirstSettingsUpdate
): Promise<RedemptionConfig> {
  return apiJson(
    API_ENDPOINTS.events.updateFirstSettings,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新頭香公告設定失敗' }
  )
}
