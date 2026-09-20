import { apiCache } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export type BotInviteState = 'pending' | 'authorized' | 'declined' | 'expired'
export type TwitchAuthorizationStatus =
  'valid' | 'requires_reauthorization' | 'temporarily_unavailable' | 'not_checked'

export interface AuthorizationHealth {
  status: TwitchAuthorizationStatus
  last_checked_at: string | null
  last_validated_at: string | null
  error_code: string | null
}

export interface AuthorizationRemovalResult {
  credential_retained: boolean
  upstream_revoke_confirmed: boolean
}

export interface BroadcasterAuthorization extends AuthorizationHealth {
  channel_id: string
  channel_name: string
  display_name: string | null
  enabled: boolean
}

export interface BotAccount {
  platform_user_id: string
  login: string
  display_name: string
  avatar: string | null
  is_system_default: boolean
  requires_reauth: boolean
  last_validated_at: string | null
  revoked_at: string | null
  authorization_status: TwitchAuthorizationStatus
  last_checked_at: string | null
  linked_at: string | null
  is_active: boolean
  is_desired: boolean
}

export interface BotInviteCreated {
  invite_id: string
  public_url: string
  expires_at: string
}

export interface BotInviteStatus {
  invite_id: string
  status: BotInviteState
  expires_at: string
  consumed_at: string | null
  account: BotAccount | null
}

export interface PublicBotInvite {
  channel_name: string
  display_name: string | null
  purpose: 'link_new' | 'reauthorize' | 'system_default_reset'
  status: BotInviteState
  expires_at: string
  required_scopes: string[]
  oauth_url: string | null
}

async function readJson<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) throw await parseApiError(response, fallback)
  return response.json() as Promise<T>
}

export async function listBotAccounts(channelId: string): Promise<BotAccount[]> {
  const response = await apiFetch(API_ENDPOINTS.tenants.botAccounts(channelId), {
    credentials: 'include',
  })
  const payload = await readJson<{ accounts: BotAccount[] }>(response, '載入 Bot 帳號失敗')
  return payload.accounts
}

export function createBotInvite(channelId: string): Promise<BotInviteCreated> {
  return apiFetch(API_ENDPOINTS.tenants.botInvites(channelId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Niibot-Action': 'bot-account-management' },
  }).then(response => readJson(response, '建立 Bot 邀請失敗'))
}

export function createBotReauthorizationInvite(
  channelId: string,
  botUserId: string
): Promise<BotInviteCreated> {
  return apiFetch(API_ENDPOINTS.tenants.reauthorizeBot(channelId, botUserId), {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Niibot-Action': 'bot-account-management' },
  }).then(response => readJson(response, '建立 Bot 重新授權邀請失敗'))
}

export function getBotInviteStatus(channelId: string, inviteId: string): Promise<BotInviteStatus> {
  return apiFetch(API_ENDPOINTS.tenants.botInviteStatus(channelId, inviteId), {
    credentials: 'include',
  }).then(response => readJson(response, '讀取 Bot 邀請狀態失敗'))
}

export function getPublicBotInvite(publicToken: string, nonce: string): Promise<PublicBotInvite> {
  return apiFetch(API_ENDPOINTS.publicBotInvites.get(publicToken, nonce)).then(response =>
    readJson(response, '讀取 Bot 邀請失敗')
  )
}

export function declineBotInvite(
  publicToken: string,
  nonce: string
): Promise<{ status: 'declined' }> {
  return apiFetch(API_ENDPOINTS.publicBotInvites.decline(publicToken, nonce), {
    method: 'POST',
  }).then(response => readJson(response, '拒絕 Bot 邀請失敗'))
}

export function createSystemBotResetInvite(): Promise<BotInviteCreated> {
  return apiFetch(API_ENDPOINTS.admin.resetSystemBot, {
    method: 'POST',
    credentials: 'include',
    headers: { 'X-Niibot-Action': 'bot-account-management' },
  }).then(response => readJson(response, '建立 Niibot reset 邀請失敗'))
}

const authorizationHeaders = {
  'X-Niibot-Action': 'twitch-authorization-management',
}

export function checkBotAuthorization(
  channelId: string,
  botUserId: string
): Promise<AuthorizationHealth> {
  return apiFetch(API_ENDPOINTS.tenants.botAuthorizationCheck(channelId, botUserId), {
    method: 'POST',
    credentials: 'include',
    headers: authorizationHeaders,
  }).then(response => readJson(response, '重新檢查 Bot 授權失敗'))
}

export function unlinkBotAccount(
  channelId: string,
  botUserId: string
): Promise<AuthorizationRemovalResult> {
  return apiFetch(API_ENDPOINTS.tenants.botAccount(channelId, botUserId), {
    method: 'DELETE',
    credentials: 'include',
    headers: authorizationHeaders,
  }).then(response => readJson(response, '移除 Bot 帳號失敗'))
}

export function getBroadcasterAuthorization(channelId: string): Promise<BroadcasterAuthorization> {
  return apiFetch(API_ENDPOINTS.tenants.broadcasterAuthorization(channelId), {
    credentials: 'include',
  }).then(response => readJson(response, '載入 Twitch 授權失敗'))
}

export function checkBroadcasterAuthorization(channelId: string): Promise<AuthorizationHealth> {
  return apiFetch(API_ENDPOINTS.tenants.broadcasterAuthorizationCheck(channelId), {
    method: 'POST',
    credentials: 'include',
    headers: authorizationHeaders,
  }).then(response => readJson(response, '重新檢查 Twitch 授權失敗'))
}

export async function disconnectBroadcasterAuthorization(
  channelId: string
): Promise<AuthorizationRemovalResult> {
  const response = await apiFetch(API_ENDPOINTS.tenants.broadcasterAuthorization(channelId), {
    method: 'DELETE',
    credentials: 'include',
    headers: authorizationHeaders,
  })
  const result = await readJson<AuthorizationRemovalResult>(response, '解除 Twitch 授權失敗')
  apiCache.clear()
  return result
}
