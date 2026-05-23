import { API_ENDPOINTS, apiFetch } from './config'

export type ModStatus = 'mod' | 'no_mod' | 'token_error' | 'scope_error' | 'broadcaster'
export type BotTokenStatus = 'ok' | 'missing' | 'no_token'

export interface AdminChannel {
  id: string
  name: string
  display_name: string
  avatar: string
  offline_image_url: string
  is_live: boolean
  mod_status: ModStatus
  is_bot: boolean
  granted_scopes: string[]
  missing_scopes: string[]
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
  id: number
  platform_user_id: string
  display_name: string | null
  username: string | null
  avatar: string | null
  note: string
  created_at: string
}

export async function getAdminChannels(): Promise<AdminChannel[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.channels, { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to fetch admin channels')
  return response.json()
}

export async function getAdminBotStatus(): Promise<BotTokenInfo> {
  const response = await apiFetch(API_ENDPOINTS.admin.botStatus, { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to fetch bot status')
  return response.json()
}

export async function getPendingActivationCodes(): Promise<PendingCode[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.activationCodes, { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to fetch pending codes')
  return response.json()
}

export async function revokeActivationCode(platformUserId: string): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.revokeActivationCode(platformUserId), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to revoke code')
}

export async function getActivationRequests(): Promise<ActivationRequest[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.activationRequests, {
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to fetch activation requests')
  return response.json()
}

export async function approveActivationRequest(id: number): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.approveRequest(id), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to approve request')
}

export async function rejectActivationRequest(id: number): Promise<void> {
  const response = await apiFetch(API_ENDPOINTS.admin.rejectRequest(id), {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error('Failed to reject request')
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

export interface ContainerLogs {
  container: string
  lines: LogLine[]
}

export async function getLogContainers(): Promise<LogContainer[]> {
  const response = await apiFetch(API_ENDPOINTS.admin.logContainers, { credentials: 'include' })
  if (!response.ok) throw new Error('Failed to fetch containers')
  return response.json()
}

export interface DbQueryResult {
  columns: string[]
  rows: (string | number | boolean | null)[][]
  row_count: number
  duration_ms: number
}

export async function runDbQuery(sql: string): Promise<DbQueryResult> {
  const response = await apiFetch(API_ENDPOINTS.admin.dbQuery, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sql }),
  })
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Query failed')
  }
  return response.json()
}

export async function getContainerLogs(
  container: string,
  tail = 200,
  since?: number
): Promise<ContainerLogs> {
  const params = new URLSearchParams({ tail: String(tail) })
  if (since !== undefined) params.set('since', String(since))
  const url = `${API_ENDPOINTS.admin.containerLogs(container)}?${params}`
  const response = await apiFetch(url, { credentials: 'include' })
  if (!response.ok) throw new Error(`Failed to fetch logs for ${container}`)
  return response.json()
}
