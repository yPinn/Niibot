import { API_ENDPOINTS } from './config'

export interface VideoQueueEntry {
  id: number
  video_id: string
  title: string | null
  duration_seconds: number | null
  requested_by: string
  started_at: string | null
}

export interface PublicVideoQueueState {
  enabled: boolean
  current: VideoQueueEntry | null
  queue: VideoQueueEntry[]
  queue_size: number
  total_queued_duration: number | null
}

export interface VideoQueueSettings {
  channel_id: string
  enabled: boolean
  min_role_chat: string
  max_duration_seconds: number
  max_queue_size: number
}

export interface VideoQueueSettingsUpdate {
  enabled?: boolean
  min_role_chat?: string
  max_duration_seconds?: number
  max_queue_size?: number
}

// ---- Public (OBS Overlay) ----

export async function getPublicVideoQueueState(username: string): Promise<PublicVideoQueueState> {
  const response = await fetch(API_ENDPOINTS.videoQueue.public(username))
  if (!response.ok) throw new Error(`Failed to fetch video queue state: ${response.statusText}`)
  return response.json()
}

export async function advanceVideoQueue(
  username: string,
  doneId: number | null
): Promise<PublicVideoQueueState> {
  const response = await fetch(API_ENDPOINTS.videoQueue.advance(username), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ done_id: doneId }),
  })
  if (!response.ok) throw new Error(`Failed to advance video queue: ${response.statusText}`)
  return response.json()
}

export async function reportVideoMetadata(
  username: string,
  entryId: number,
  durationSeconds: number
): Promise<void> {
  await fetch(API_ENDPOINTS.videoQueue.metadata(username, entryId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ duration_seconds: durationSeconds }),
  })
}

// ---- Authenticated (Dashboard) ----

export async function getVideoQueueState(): Promise<PublicVideoQueueState> {
  const response = await fetch(API_ENDPOINTS.videoQueue.state, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to fetch video queue state: ${response.statusText}`)
  return response.json()
}

export async function skipCurrentVideo(): Promise<PublicVideoQueueState> {
  const response = await fetch(API_ENDPOINTS.videoQueue.skip, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to skip video: ${response.statusText}`)
  return response.json()
}

export async function clearVideoQueue(): Promise<PublicVideoQueueState> {
  const response = await fetch(API_ENDPOINTS.videoQueue.clear, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to clear video queue: ${response.statusText}`)
  return response.json()
}

export async function getVideoQueueSettings(): Promise<VideoQueueSettings> {
  const response = await fetch(API_ENDPOINTS.videoQueue.settings, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to fetch video queue settings: ${response.statusText}`)
  return response.json()
}

export async function updateVideoQueueSettings(
  data: VideoQueueSettingsUpdate
): Promise<VideoQueueSettings> {
  const response = await fetch(API_ENDPOINTS.videoQueue.settings, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update video queue settings: ${response.statusText}`)
  return response.json()
}
