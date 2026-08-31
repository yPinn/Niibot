import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export type TenantRole = 'owner' | 'manager'
export type TenantCapability =
  | 'edit_operations'
  | 'switch_bot'
  | 'toggle_bot'
  | 'manage_bot_accounts'
  | 'manage_members'
  | 'manage_billing'
  | 'manage_security'

export interface Tenant {
  channel_id: string
  channel_name: string
  display_name: string | null
  enabled: boolean
  role: TenantRole
  capabilities: TenantCapability[]
}

interface TenantListResponse {
  tenants: Tenant[]
}

async function fetchTenants(): Promise<Tenant[]> {
  const response = await apiFetch(API_ENDPOINTS.tenants.list, {
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '載入可管理頻道失敗')
  const payload = (await response.json()) as TenantListResponse
  return payload.tenants
}

export async function getTenants(options?: { forceRefresh?: boolean }): Promise<Tenant[]> {
  return apiCache.fetch(CACHE_KEYS.TENANTS, fetchTenants, {
    ttl: 5 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}
