import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface VipSettings {
  channel_id: string
  slot_limit: number | null
  tracking_started_at: string | null
  last_full_sync_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface VipRewardRule {
  id: number | null
  channel_id: string
  reward_id: string
  reward_name_snapshot: string
  duration_months: number | null
  is_permanent: boolean
  enabled: boolean
}

export interface VipEntitlement {
  id: number
  channel_id: string
  user_id: string
  user_login: string
  display_name: string | null
  source: 'external_baseline' | 'external_event' | 'managed'
  status: 'active' | 'expired' | 'removed_external' | 'released'
  granted_at: string | null
  expires_at: string | null
  is_permanent: boolean
  last_reward_rule_id: number | null
  last_synced_at: string
}

export interface VipRedemptionEvent {
  id: number
  redemption_id: string
  reward_id: string
  reward_name_snapshot: string
  user_id: string
  user_login: string
  display_name: string | null
  duration_months_snapshot: number | null
  is_permanent_snapshot: boolean
  status: string
  error_code: string | null
  occurred_at: string
  processed_at: string | null
}

export interface VipState {
  settings: VipSettings
  rules: VipRewardRule[]
  entitlements: VipEntitlement[]
  redemptions: VipRedemptionEvent[]
}

const mutationHeaders = {
  'Content-Type': 'application/json',
  'X-Niibot-Action': 'vip-management',
}

export function getVipState(): Promise<VipState> {
  return apiJson(
    API_ENDPOINTS.vip.state,
    { credentials: 'include' },
    { fallback: '載入 VIP 管理資料失敗' }
  )
}

export function initializeVipTracking(slotLimit: number): Promise<VipSettings> {
  return apiJson(
    API_ENDPOINTS.vip.initialize,
    {
      method: 'POST',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify({ slot_limit: slotLimit }),
    },
    { fallback: 'VIP 初次清點失敗' }
  )
}

export function updateVipSlotLimit(slotLimit: number): Promise<VipSettings> {
  return apiJson(
    API_ENDPOINTS.vip.settings,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify({ slot_limit: slotLimit }),
    },
    { fallback: '更新 VIP 上限失敗' }
  )
}

export function syncVipState(): Promise<void> {
  return apiJson(
    API_ENDPOINTS.vip.sync,
    { method: 'POST', credentials: 'include', headers: mutationHeaders },
    { fallback: '重新清點 Twitch VIP 失敗' }
  )
}

export function upsertVipRule(
  rewardId: string,
  update: { duration_months: number | null; is_permanent: boolean; enabled: boolean }
): Promise<VipRewardRule> {
  return apiJson(
    API_ENDPOINTS.vip.rule(rewardId),
    {
      method: 'PUT',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify(update),
    },
    { fallback: '更新 VIP Reward 規則失敗' }
  )
}

export function setVipRulesEnabled(enabled: boolean): Promise<VipRewardRule[]> {
  return apiJson(
    API_ENDPOINTS.vip.rulesEnabled,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify({ enabled }),
    },
    { fallback: '切換 VIP Reward 規則失敗' }
  )
}

export function adoptExternalVip(
  redemptionId: string,
  durationMonths: number | null,
  isPermanent: boolean
): Promise<VipEntitlement> {
  return apiJson(
    API_ENDPOINTS.vip.adopt(redemptionId),
    {
      method: 'POST',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify({ duration_months: durationMonths, is_permanent: isPermanent }),
    },
    { fallback: '納入 VIP 期限管理失敗' }
  )
}

export function keepExternalVip(redemptionId: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.vip.keepExternal(redemptionId),
    { method: 'POST', credentials: 'include', headers: mutationHeaders },
    { fallback: '更新 VIP 待審狀態失敗' }
  )
}

export function adjustVipEntitlement(
  userId: string,
  durationMonths: number | null,
  isPermanent: boolean
): Promise<VipEntitlement> {
  return apiJson(
    API_ENDPOINTS.vip.entitlement(userId),
    {
      method: 'PATCH',
      credentials: 'include',
      headers: mutationHeaders,
      body: JSON.stringify({ duration_months: durationMonths, is_permanent: isPermanent }),
    },
    { fallback: '調整 VIP 預計期限失敗' }
  )
}

export function removeVipEntitlement(userId: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.vip.entitlement(userId),
    {
      method: 'DELETE',
      credentials: 'include',
      headers: mutationHeaders,
    },
    { fallback: '移除 Twitch VIP 失敗' }
  )
}
