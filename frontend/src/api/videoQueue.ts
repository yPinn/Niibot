import { API_ENDPOINTS, apiFetch } from './config'

export interface VideoQueueEntry {
  id: number
  video_id: string
  title: string | null
  duration_seconds: number | null
  is_vertical: boolean
  requested_by: string
  source: string
  video_type: 'youtube' | 'twitch_clip'
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
  redemption_enabled: boolean
  max_duration_redemption: number
  max_queue_size: number
  min_view_count: number
  user_cooldown_seconds: number
  max_per_user: number
}

export interface VideoQueueSettingsUpdate {
  enabled?: boolean
  redemption_enabled?: boolean
  max_duration_redemption?: number
  max_queue_size?: number
  min_view_count?: number
  user_cooldown_seconds?: number
  max_per_user?: number
}

// ---- Public (OBS Overlay) ----

export async function getPublicVideoQueueState(username: string): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.public(username))
  if (!response.ok) throw new Error(`Failed to fetch video queue state: ${response.statusText}`)
  return response.json()
}

export async function advanceVideoQueue(
  username: string,
  doneId: number | null
): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.advance(username), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ done_id: doneId }),
  })
  if (!response.ok) throw new Error(`Failed to advance video queue: ${response.statusText}`)
  return response.json()
}

// Best-effort: callers swallow errors (.catch(() => {})). No response.ok check is intentional.
export async function reportVideoMetadata(
  username: string,
  entryId: number,
  durationSeconds: number
): Promise<void> {
  await apiFetch(API_ENDPOINTS.videoQueue.metadata(username, entryId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ duration_seconds: durationSeconds }),
  })
}

// ---- Authenticated (Dashboard) ----

export async function getVideoQueueState(): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.state, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to fetch video queue state: ${response.statusText}`)
  return response.json()
}

export async function skipCurrentVideo(): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.skip, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to skip video: ${response.statusText}`)
  return response.json()
}

export async function clearVideoQueue(): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.clear, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to clear video queue: ${response.statusText}`)
  return response.json()
}

export async function getVideoQueueSettings(): Promise<VideoQueueSettings> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.settings, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to fetch video queue settings: ${response.statusText}`)
  return response.json()
}

export async function updateVideoQueueSettings(
  data: VideoQueueSettingsUpdate
): Promise<VideoQueueSettings> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.settings, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!response.ok) throw new Error(`Failed to update video queue settings: ${response.statusText}`)
  return response.json()
}

export async function setVideoAsNext(entryId: number): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.setNext(entryId), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to set entry as next: ${response.statusText}`)
  return response.json()
}

export async function playVideoNow(entryId: number): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.playNow(entryId), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Failed to play entry now: ${response.statusText}`)
  return response.json()
}

export async function addVideoToQueue(url: string): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.addEntry, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ url }),
  })
  if (response.status === 409) {
    const body = await response.json().catch(() => ({}))
    // detail strings are coupled to backend literals:
    //   "Video already in queue"  → video_queue_router.py
    //   "Queue is full"           → video_queue_router.py
    const detail: string = body?.detail ?? ''
    if (detail === 'Video already in queue') throw new Error('該影片已在佇列中')
    else if (detail === 'Queue is full') throw new Error('隊列已滿')
    else throw new Error(detail || '新增失敗，請稍後再試')
  }
  if (response.status === 422) throw new Error('無效的 YouTube 或 Twitch Clip 連結')
  if (!response.ok) throw new Error('新增失敗，請稍後再試')
  return response.json()
}
