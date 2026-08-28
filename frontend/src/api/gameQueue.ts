import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface QueueEntry {
  id: number
  channel_id: string
  user_id: string
  user_name: string
  redeemed_at: string
  position: number
  batch: number
}

export interface QueueState {
  current_batch: QueueEntry[]
  next_batch: QueueEntry[]
  full_queue: QueueEntry[]
  group_size: number
  enabled: boolean
  total_active: number
}

export interface PublicQueueState {
  current_batch: QueueEntry[]
  next_batch: QueueEntry[]
  group_size: number
  enabled: boolean
  total_active: number
}

export interface QueueSettings {
  id: number
  channel_id: string
  group_size: number
  enabled: boolean
}

export interface QueueSettingsUpdate {
  group_size?: number
  enabled?: boolean
}

export interface ClearResponse extends QueueState {
  cleared_count: number
}

const authed = { credentials: 'include' } as const

// ---- Queue State ----

export function getQueueState(): Promise<QueueState> {
  return apiJson(API_ENDPOINTS.gameQueue.state, authed, { fallback: '載入排隊清單失敗' })
}

export function advanceBatch(): Promise<QueueState> {
  return apiJson(
    API_ENDPOINTS.gameQueue.advance,
    { method: 'POST', ...authed },
    { fallback: '換下一批失敗' }
  )
}

export function removePlayer(entryId: number): Promise<QueueState> {
  return apiJson(
    API_ENDPOINTS.gameQueue.removeEntry(entryId),
    { method: 'DELETE', ...authed },
    { fallback: '移除玩家失敗' }
  )
}

export function promotePlayer(entryId: number): Promise<QueueState> {
  return apiJson(
    API_ENDPOINTS.gameQueue.promoteEntry(entryId),
    { method: 'POST', ...authed },
    { fallback: '提前玩家失敗' }
  )
}

export function clearQueue(): Promise<ClearResponse> {
  return apiJson(
    API_ENDPOINTS.gameQueue.clear,
    { method: 'DELETE', ...authed },
    { fallback: '清空排隊清單失敗' }
  )
}

// ---- Settings ----

export function getQueueSettings(): Promise<QueueSettings> {
  return apiJson(API_ENDPOINTS.gameQueue.settings, authed, { fallback: '載入排隊設定失敗' })
}

export function updateQueueSettings(data: QueueSettingsUpdate): Promise<QueueSettings> {
  return apiJson(
    API_ENDPOINTS.gameQueue.settings,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      ...authed,
      body: JSON.stringify(data),
    },
    { fallback: '更新排隊設定失敗' }
  )
}

// ---- Public (OBS Overlay) ----

export function getPublicQueueState(username: string): Promise<PublicQueueState> {
  return apiJson(API_ENDPOINTS.gameQueue.public(username), undefined, {
    fallback: '載入排隊狀態失敗',
  })
}
