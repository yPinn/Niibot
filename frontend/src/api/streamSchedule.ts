import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export type ScheduleKind = 'recurring' | 'one_off'
export type OccurrenceExceptionKind = 'cancelled' | 'replacement'

export interface StreamScheduleSettings {
  channel_id: string
  timezone: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface StreamScheduleSettingsUpdate {
  timezone?: string
  enabled?: boolean
}

export interface StreamSchedulePublishStatus {
  status: 'idle' | 'pending' | 'synced' | 'blocked' | 'error'
  pending_count: number
  synced_count: number
  blocked_count: number
  error_count: number
  last_error_code: string | null
  last_synced_at: string | null
}

export interface StreamSchedule {
  id: number
  channel_id: string
  kind: ScheduleKind
  weekday: number | null // 0 = Monday, only set when kind === 'recurring'
  specific_date: string | null // only set when kind === 'one_off'
  start_time: string // "HH:MM:SS"
  duration_minutes: number
  title_template: string
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface StreamScheduleCreate {
  kind: ScheduleKind
  weekday?: number | null
  specific_date?: string | null
  start_time: string
  duration_minutes: number
  title_template?: string
  game_id?: string
  game_name?: string
}

export interface StreamScheduleUpdate {
  start_time?: string
  duration_minutes?: number
  title_template?: string
  enabled?: boolean
}

export interface StreamScheduleSegment {
  id: number
  channel_id: string
  schedule_id: number
  offset_minutes: number
  title_template: string
  game_id: string | null
  game_name: string | null
  sort_order: number
}

export interface StreamScheduleSegmentCreate {
  offset_minutes: number
  title_template?: string
  /** Pick from searchStreamScheduleGames() — both fields must be set together, or both omitted for no game. */
  game_id?: string
  game_name?: string
  sort_order?: number
}

export interface StreamScheduleSegmentUpdate {
  offset_minutes?: number
  title_template?: string
  /** Omit both to leave the game unchanged; pass "" for both to explicitly clear it;
   * or set both together from a searchStreamScheduleGames() pick. */
  game_id?: string
  game_name?: string
  sort_order?: number
}

export interface StreamScheduleOccurrenceException {
  id: number
  channel_id: string
  recurring_schedule_id: number
  occurrence_date: string
  kind: OccurrenceExceptionKind
  replacement_schedule_id: number | null
  created_at: string | null
  updated_at: string | null
}

export interface StreamScheduleReplacement {
  exception: StreamScheduleOccurrenceException
  schedule: StreamSchedule
}

export interface StreamScheduleGameSearchResult {
  id: string
  name: string
  box_art_url: string | null
}

export function getStreamScheduleSettings(): Promise<StreamScheduleSettings> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.settings,
    { credentials: 'include' },
    { fallback: '載入排程設定失敗' }
  )
}

export function getStreamSchedulePublishStatus(): Promise<StreamSchedulePublishStatus> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.twitchPublish,
    { credentials: 'include' },
    { fallback: '載入 Twitch 行程表同步狀態失敗' }
  )
}

export function retryStreamSchedulePublish(): Promise<{ status: 'queued' }> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.twitchPublishRetry,
    {
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'stream-schedule-publish-retry' },
    },
    { fallback: '重新同步 Twitch 行程表失敗' }
  )
}

export function updateStreamScheduleSettings(
  data: StreamScheduleSettingsUpdate
): Promise<StreamScheduleSettings> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.settings,
    {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'stream-schedule-settings',
      },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新排程設定失敗' }
  )
}

export function getStreamSchedules(): Promise<StreamSchedule[]> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.schedules,
    { credentials: 'include' },
    { fallback: '載入排程失敗' }
  )
}

export function getStreamScheduleOccurrenceExceptions(): Promise<
  StreamScheduleOccurrenceException[]
> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.occurrenceExceptions,
    { credentials: 'include' },
    { fallback: '載入本次調整失敗' }
  )
}

export function cancelStreamScheduleOccurrence(
  scheduleId: number,
  date: string
): Promise<StreamScheduleOccurrenceException> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.occurrenceCancel(scheduleId, date),
    {
      method: 'POST',
      headers: { 'X-Niibot-Action': 'stream-schedule-occurrence-cancel' },
      credentials: 'include',
    },
    { fallback: '取消本次排程失敗' }
  )
}

export function restoreStreamScheduleOccurrence(scheduleId: number, date: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.occurrenceRestore(scheduleId, date),
    {
      method: 'DELETE',
      headers: { 'X-Niibot-Action': 'stream-schedule-occurrence-restore' },
      credentials: 'include',
    },
    { fallback: '恢復本次排程失敗' }
  )
}

export function replaceStreamScheduleOccurrence(
  scheduleId: number,
  date: string
): Promise<StreamScheduleReplacement> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.occurrenceReplace(scheduleId, date),
    {
      method: 'POST',
      headers: { 'X-Niibot-Action': 'stream-schedule-occurrence-replace' },
      credentials: 'include',
    },
    { fallback: '建立本次調整失敗' }
  )
}

export function createStreamSchedule(data: StreamScheduleCreate): Promise<StreamSchedule> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.schedules,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Niibot-Action': 'stream-schedule-create' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '建立排程失敗' }
  )
}

export function updateStreamSchedule(
  id: number,
  data: StreamScheduleUpdate
): Promise<StreamSchedule> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.schedule(id),
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json', 'X-Niibot-Action': 'stream-schedule-update' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新排程失敗' }
  )
}

export function deleteStreamSchedule(id: number): Promise<void> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.schedule(id),
    {
      method: 'DELETE',
      headers: { 'X-Niibot-Action': 'stream-schedule-delete' },
      credentials: 'include',
    },
    { fallback: '刪除排程失敗' }
  )
}

export function getStreamScheduleSegments(scheduleId: number): Promise<StreamScheduleSegment[]> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.segments(scheduleId),
    { credentials: 'include' },
    { fallback: '載入排程區塊失敗' }
  )
}

export function createStreamScheduleSegment(
  scheduleId: number,
  data: StreamScheduleSegmentCreate
): Promise<StreamScheduleSegment> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.segments(scheduleId),
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'stream-schedule-segment-create',
      },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '新增排程區塊失敗' }
  )
}

export function updateStreamScheduleSegment(
  id: number,
  data: StreamScheduleSegmentUpdate
): Promise<StreamScheduleSegment> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.segment(id),
    {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'stream-schedule-segment-update',
      },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新排程區塊失敗' }
  )
}

export function searchStreamScheduleGames(
  query: string
): Promise<StreamScheduleGameSearchResult[]> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.gamesSearch(query),
    { credentials: 'include' },
    { fallback: '搜尋遊戲分類失敗' }
  )
}

export function deleteStreamScheduleSegment(id: number): Promise<void> {
  return apiJson(
    API_ENDPOINTS.streamSchedule.segment(id),
    {
      method: 'DELETE',
      headers: { 'X-Niibot-Action': 'stream-schedule-segment-delete' },
      credentials: 'include',
    },
    { fallback: '刪除排程區塊失敗' }
  )
}
