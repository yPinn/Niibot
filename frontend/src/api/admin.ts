import { API_ENDPOINTS, apiFetch } from './config'

export type ModStatus = 'mod' | 'no_mod' | 'token_error' | 'scope_error'

export interface AdminChannel {
  id: string
  name: string
  display_name: string
  avatar: string
  is_live: boolean
  mod_status: ModStatus
}

export interface PendingCode {
  platform_user_id: string
  display_name: string | null
  username: string | null
  avatar: string | null
  expires_at: string
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
