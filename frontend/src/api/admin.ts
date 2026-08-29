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

export type GrantKind = 'channel_points' | 'owner_manual'
export type GrantStatus = 'issued' | 'consumed' | 'expired' | 'revoked'

export interface Grant {
  id: number
  kind: GrantKind
  status: GrantStatus
  platform_user_id: string | null
  code_plain: string | null
  reward_cost: number | null
  channel_id: string | null
  redemption_id: string | null
  issued_at: string
  expires_at: string
  used_at: string | null
  attempt_count: number
  display_name: string | null
  avatar: string | null
  username: string | null
}

export interface GrantKindCounts {
  kind: GrantKind
  issued_7d: number
  consumed_7d: number
  issued_30d: number
  consumed_30d: number
  issued_all: number
  consumed_all: number
  outstanding: number
}

export interface OnboardingFunnel {
  active_members: number
  by_kind: GrantKindCounts[]
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

export async function getGrants(params?: {
  kind?: GrantKind
  status?: GrantStatus
}): Promise<Grant[]> {
  const qs = new URLSearchParams()
  if (params?.kind) qs.set('kind', params.kind)
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs}` : ''
  const response = await apiFetch(API_ENDPOINTS.admin.grants(suffix), { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入啟用碼失敗')
  return response.json()
}

export async function createOwnerCode(): Promise<string> {
  const response = await apiFetch(API_ENDPOINTS.admin.grants(), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '產生啟用碼失敗')
  return (await response.json()).code
}

export async function revokeGrant(grantId: number): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.revokeGrant(grantId), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '撤銷啟用碼失敗')
}

export async function getOnboardingFunnel(): Promise<OnboardingFunnel> {
  const response = await apiFetch(API_ENDPOINTS.admin.onboardingFunnel, { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入啟用漏斗失敗')
  return response.json()
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

// ── Client error telemetry (frontend errors, grouped by fingerprint) ──────────

export type ClientErrorKind = 'error' | 'unhandledrejection' | 'react' | 'api'

export interface ClientErrorGroup {
  fingerprint: string
  count: number
  first_seen: string
  last_seen: string
  kind: ClientErrorKind
  message: string
  route: string | null
  error_code: string | null
  http_status: number | null
  app_version: string | null
  request_id: string | null
}

export interface ClientErrorEvent {
  occurred_at: string
  kind: ClientErrorKind
  message: string
  stack: string | null
  component_stack: string | null
  url: string
  route: string | null
  request_id: string | null
  error_code: string | null
  http_status: number | null
  user_id: string | null
  user_agent: string | null
  app_version: string | null
}

export async function getClientErrorGroups(
  opts: { sinceHours?: number; kind?: ClientErrorKind } = {}
): Promise<ClientErrorGroup[]> {
  const params = new URLSearchParams()
  if (opts.sinceHours !== undefined) params.set('since_hours', String(opts.sinceHours))
  if (opts.kind) params.set('kind', opts.kind)
  const qs = params.toString() ? `?${params}` : ''
  const response = await apiFetch(API_ENDPOINTS.admin.clientErrors(qs), { credentials: 'include' })
  if (!response.ok) throw await parseApiError(response, '載入前端錯誤失敗')
  return response.json()
}

export async function getClientErrorEvents(fingerprint: string): Promise<ClientErrorEvent[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.clientErrorEvents(fingerprint), {
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '載入錯誤明細失敗')
  return response.json()
}
