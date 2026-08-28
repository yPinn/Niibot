import type { EmoteItem } from './aiSettings'
import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export type ModStatus = 'mod' | 'no_mod' | 'token_error' | 'scope_error' | 'broadcaster'
export type BotTokenStatus = 'ok' | 'missing' | 'no_token'

export type ChannelMembershipStatus = 'active' | 'pending' | 'suspended'

export interface AdminChannel {
  id: string
  name: string
  display_name: string
  avatar: string
  offline_image_url: string
  is_live: boolean
  is_enabled: boolean
  mod_status: ModStatus
  is_bot: boolean
  granted_scopes: string[]
  missing_scopes: string[]
  membership_status: ChannelMembershipStatus
  owner_user_id: string | null
}

export interface BotTokenInfo {
  id: string
  name: string
  display_name: string
  avatar: string
  status: BotTokenStatus
  granted_scopes: string[]
  missing_scopes: string[]
}

export interface PendingCode {
  platform_user_id: string
  display_name: string | null
  username: string | null
  avatar: string | null
  expires_at: string
  code_plain: string | null
}

export interface ActivationRequest {
  /** User UUID (was previously the int activation_requests.id). */
  id: string
  platform_user_id: string
  display_name: string | null
  username: string | null
  avatar: string | null
  note: string
  created_at: string
}

export interface MembershipEvent {
  id: number
  event_type:
    | 'requested'
    | 'auto_admitted'
    | 'approved'
    | 'rejected'
    | 'suspended'
    | 'reinstated'
    | 'withdrawn'
  actor_type: 'system' | 'owner' | 'user'
  actor_user_id: string | null
  reason: string | null
  metadata: Record<string, unknown>
  occurred_at: string
}

export async function getAdminChannels(): Promise<AdminChannel[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.channels, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入頻道清單失敗')
  return response.json()
}

export async function getAdminBotStatus(): Promise<BotTokenInfo> {
  const response = await apiFetch(API_ENDPOINTS.admin.botStatus, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入 Bot 狀態失敗')
  return response.json()
}

export interface BotEmoteChannel {
  channel_id: string
  name: string
  display_name: string
  avatar: string
  available_count: number
  total_count: number
  /** Bot holds a real subscription to this channel (authoritative, not inferred from emotes). */
  is_subscribed: boolean
  emotes: EmoteItem[]
}

export interface BotEmoteResync {
  channel_id: string
  synced: boolean
  available_count: number
}

export async function getBotEmotes(): Promise<BotEmoteChannel[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.botEmotes, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入 Bot 表情失敗')
  return response.json()
}

export async function resyncBotEmotes(channelId?: string): Promise<BotEmoteResync[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.resyncBotEmotes(channelId), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '重新同步 Bot 表情失敗')
  return response.json()
}

export async function getPendingActivationCodes(): Promise<PendingCode[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.activationCodes, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入待啟用代碼失敗')
  return response.json()
}

export async function revokeActivationCode(platformUserId: string): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.revokeActivationCode(platformUserId), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '撤銷代碼失敗')
}

export async function getActivationRequests(): Promise<ActivationRequest[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.activationRequests, {
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '載入啟用申請失敗')
  return response.json()
}

export async function approveActivationRequest(userId: string, reason: string = ''): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.approveRequest(userId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!response.ok) throw await parseApiError(response, '核准申請失敗')
}

export async function rejectActivationRequest(userId: string, reason: string = ''): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.rejectRequest(userId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!response.ok) throw await parseApiError(response, '駁回申請失敗')
}

export async function getMembershipTimeline(userId: string): Promise<MembershipEvent[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.membershipTimeline(userId), {
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '載入會員紀錄失敗')
  return response.json()
}

export async function reinstateMembership(userId: string, reason: string = ''): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.reinstateMembership(userId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  })
  if (!response.ok) throw await parseApiError(response, '恢復會員失敗')
}

export interface LogContainer {
  name: string
  label: string
  running: boolean
}

export interface LogLine {
  stream: 'stdout' | 'stderr'
  text: string
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL' | 'UNKNOWN'

export interface LogRecord {
  stream: 'stdout' | 'stderr'
  ts: string
  level: LogLevel
  source: 'json' | 'postgres' | 'raw'
  message: string
  logger: string
  mod: string
  own: boolean
  service: string
  request_id: string | null
  channel: string | null
  code: string | null
  pid: string | null
  exception: string | null
  extra: Record<string, unknown>
  raw: string
}

export interface ContainerLogs {
  container: string
  /** @deprecated use `records` */
  lines: LogLine[]
  records: LogRecord[]
}

export async function getLogContainers(): Promise<LogContainer[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.logContainers, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入容器清單失敗')
  return response.json()
}

export interface DbQueryResult {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  row_count: number
  duration_ms: number
}

export async function getModuleAIPacks(): Promise<string[]> {
  const res = await apiFetch(API_ENDPOINTS.admin.moduleAiPacks, { credentials: 'include' })
  if (!res.ok) throw await parseApiError(res, '載入 AI 知識包設定失敗')
  return res.json()
}

export async function setModuleAIPacks(packs: string[]): Promise<string[]> {
  const res = await apiFetch(API_ENDPOINTS.admin.moduleAiPacks, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled_packs: packs }),
  })
  if (!res.ok) throw await parseApiError(res, '更新 AI 知識包設定失敗')
  return res.json()
}

export async function runDbQuery(sql: string): Promise<DbQueryResult> {
  const response = await apiFetch(API_ENDPOINTS.admin.dbQuery, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql }),
  })
  if (!response.ok) throw await parseApiError(response, '查詢失敗')
  return response.json()
}

export async function getContainerLogs(
  container: string,
  opts: { tail?: number; since?: number; level?: string; q?: string } = {}
): Promise<ContainerLogs> {
  const params = new URLSearchParams({ tail: String(opts.tail ?? 200) })
  if (opts.since !== undefined) params.set('since', String(opts.since))
  if (opts.level && opts.level !== 'ALL') params.set('level', opts.level)
  if (opts.q) params.set('q', opts.q)
  const url = `${API_ENDPOINTS.admin.containerLogs(container)}?${params}`
  const response = await apiFetch(url, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, `讀取 ${container} 記錄失敗`)
  return response.json()
}
