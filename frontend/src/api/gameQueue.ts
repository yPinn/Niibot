import { API_ENDPOINTS } from './config'

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

// ---- Queue State ----

export async function getQueueState(): Promise<QueueState> {
  const response = await fetch(API_ENDPOINTS.gameQueue.state, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch queue state: ${response.statusText}`)
  return response.json()
}

export async function advanceBatch(): Promise<QueueState> {
  const response = await fetch(API_ENDPOINTS.gameQueue.advance, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to advance batch: ${response.statusText}`)
  return response.json()
}

export async function removePlayer(entryId: number): Promise<QueueState> {
  const response = await fetch(API_ENDPOINTS.gameQueue.removeEntry(entryId), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to remove player: ${response.statusText}`)
  return response.json()
}

export async function clearQueue(): Promise<ClearResponse> {
  const response = await fetch(API_ENDPOINTS.gameQueue.clear, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to clear queue: ${response.statusText}`)
  return response.json()
}

// ---- Settings ----

export async function getQueueSettings(): Promise<QueueSettings> {
  const response = await fetch(API_ENDPOINTS.gameQueue.settings, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to fetch queue settings: ${response.statusText}`)
  return response.json()
}

export async function updateQueueSettings(data: QueueSettingsUpdate): Promise<QueueSettings> {
  const response = await fetch(API_ENDPOINTS.gameQueue.settings, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update queue settings: ${response.statusText}`)
  return response.json()
}

// ---- Public (OBS Overlay) ----

export async function getPublicQueueState(channelId: string): Promise<PublicQueueState> {
  const response = await fetch(API_ENDPOINTS.gameQueue.public(channelId))
  if (!response.ok) throw new Error(`Failed to fetch public queue state: ${response.statusText}`)
  return response.json()
}
