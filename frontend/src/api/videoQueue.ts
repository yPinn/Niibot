import { API_ENDPOINTS, apiFetch } from './config'
import { apiJson, parseApiError } from './errors'

export type VideoType = 'youtube' | 'twitch_clip' | 'twitch_vod' | 'bilibili'

export interface VideoQueueEntry {
  id: number
  video_id: string
  title: string | null
  /** For twitch_vod this is the capped play window, not the full VOD length. */
  duration_seconds: number | null
  is_vertical: boolean
  /** Poster image URL, or null — the card then shows a placeholder. */
  thumbnail_url: string | null
  /** twitch_vod seek offset (the URL's `?t=`); 0 otherwise. */
  start_seconds: number
  requested_by: string
  source: string
  video_type: VideoType
  started_at: string | null
}

export interface PublicVideoQueueState {
  enabled: boolean
  current: VideoQueueEntry | null
  queue: VideoQueueEntry[]
  queue_size: number
  total_queued_duration: number | null
}

export interface VideoQueueHistoryEntry {
  id: number
  video_id: string
  title: string | null
  duration_seconds: number | null
  requested_by: string
  source: string
  video_type: string
  status: 'done' | 'skipped'
  started_at: string | null
  ended_at: string | null
}

export interface VideoQueueHistoryPage {
  entries: VideoQueueHistoryEntry[]
  next_cursor: string | null
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
  max_duration_seconds: number
  replay_cooldown_hours: number
}

export type BlocklistKind = 'video' | 'creator' | 'keyword' | 'user'

export interface BlocklistEntry {
  id: number
  kind: BlocklistKind
  value: string
  label: string | null
  created_at: string | null
}

export interface VideoQueueSettingsUpdate {
  enabled?: boolean
  redemption_enabled?: boolean
  max_duration_redemption?: number
  max_queue_size?: number
  min_view_count?: number
  user_cooldown_seconds?: number
  max_per_user?: number
  max_duration_seconds?: number
  replay_cooldown_hours?: number
}

// ---- Public (OBS Overlay) ----

export async function getPublicVideoQueueState(username: string): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.public(username))
  if (!response.ok) throw await parseApiError(response, '載入點播佇列失敗')
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
  if (!response.ok) throw await parseApiError(response, '播放下一部失敗')
  return response.json()
}

/**
 * Resolve a queued Twitch clip to a signed, directly-playable MP4 URL so the
 * overlay can play it in a host-controlled `<video>` (the embed iframe cannot
 * autoplay in OBS). Returns null on any failure — the caller falls back to the
 * iframe.
 */
export async function fetchTwitchClipSource(
  username: string,
  entryId: number
): Promise<string | null> {
  try {
    const response = await apiFetch(API_ENDPOINTS.videoQueue.clipSource(username, entryId))
    if (!response.ok) return null
    const data = (await response.json()) as { url?: unknown }
    return typeof data.url === 'string' ? data.url : null
  } catch {
    return null
  }
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
  if (!response.ok) throw await parseApiError(response, '載入點播佇列失敗')
  return response.json()
}

export async function skipCurrentVideo(): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.skip, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '跳過影片失敗')
  return response.json()
}

export async function clearVideoQueue(): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.clear, {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '清空點播佇列失敗')
  return response.json()
}

export async function getVideoQueueHistory(cursor?: string): Promise<VideoQueueHistoryPage> {
  const url = cursor
    ? `${API_ENDPOINTS.videoQueue.history}?cursor=${encodeURIComponent(cursor)}`
    : API_ENDPOINTS.videoQueue.history
  const response = await apiFetch(url, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入播放紀錄失敗')
  return response.json()
}

export async function getVideoQueueSettings(): Promise<VideoQueueSettings> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.settings, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入點播設定失敗')
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
  if (!response.ok) throw await parseApiError(response, '更新點播設定失敗')
  return response.json()
}

export async function setVideoAsNext(entryId: number): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.setNext(entryId), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '設為下一部失敗')
  return response.json()
}

export async function playVideoNow(entryId: number): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.playNow(entryId), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '立即播放失敗')
  return response.json()
}

export async function removeQueueEntry(entryId: number): Promise<PublicVideoQueueState> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.removeEntry(entryId), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '移除影片失敗')
  return response.json()
}

export async function getVideoQueueBlocklist(): Promise<BlocklistEntry[]> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.blocklist, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入封鎖清單失敗')
  return response.json()
}

export async function addVideoQueueBlock(
  kind: BlocklistKind,
  value: string,
  label?: string | null
): Promise<BlocklistEntry> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.blocklist, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ kind, value, label: label ?? null }),
  })
  if (!response.ok) throw await parseApiError(response, '加入封鎖清單失敗')
  return response.json()
}

export async function removeVideoQueueBlock(id: number): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.videoQueue.blocklistEntry(id), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '移除封鎖項目失敗')
}

export function addVideoToQueue(url: string): Promise<PublicVideoQueueState> {
  return apiJson(
    API_ENDPOINTS.videoQueue.addEntry,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ url }),
    },
    { fallback: '新增影片失敗' }
  )
}
