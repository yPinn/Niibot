import { API_ENDPOINTS, apiFetch } from './config'
import { apiJson, parseApiError } from './errors'

export interface CommunityOverlayEvent {
  id: number
  event_type: string
  schema_version: number
  source: string
  actor_display_name: string | null
  payload: Record<string, unknown>
  occurred_at: string
  expires_at: string | null
}

export interface CommunityOverlayFeed {
  cursor: number
  events: CommunityOverlayEvent[]
}

export interface CommunityOverlayAccess {
  public_key: string
  enabled: boolean
  created_at: string
  updated_at: string
}

export type CommunityOverlayPlacement = 'top-left' | 'top-right' | 'bottom-left' | 'bottom-right'
export type CommunityOverlayMotion = 'standard' | 'subtle' | 'none'

export interface CommunityOverlayTheme {
  surface_color: string
  accent_color: string
  text_color: string
  placement: CommunityOverlayPlacement
  radius_px: number
  display_ms: number
  motion: CommunityOverlayMotion
}

export const DEFAULT_COMMUNITY_OVERLAY_THEME: CommunityOverlayTheme = {
  surface_color: '#FFF7CF',
  accent_color: '#EF4D88',
  text_color: '#241B34',
  placement: 'bottom-right',
  radius_px: 24,
  display_ms: 5_500,
  motion: 'standard',
}

export interface CommunityOverlayPublishedTheme {
  revision_id: number | null
  renderer: string
  schema_version: number
  theme: CommunityOverlayTheme
  created_at: string | null
}

export interface CommunityOverlayThemeState {
  renderer: string
  schema_version: number
  draft_version: number
  draft: CommunityOverlayTheme
  published: CommunityOverlayPublishedTheme
  has_unpublished_changes: boolean
  updated_at: string
}

const authed = { credentials: 'include' } as const
const actionHeaders = { 'X-Niibot-Action': 'community-overlay' } as const

export async function getCommunityOverlayFeed(
  publicKey: string,
  afterId?: number
): Promise<CommunityOverlayFeed> {
  const params = new URLSearchParams()
  if (afterId !== undefined) params.set('after_id', String(afterId))
  const query = params.size ? `?${params.toString()}` : ''
  const response = await apiFetch(`${API_ENDPOINTS.communityOverlay.events}${query}`, {
    headers: { 'X-Overlay-Key': publicKey },
  })
  if (!response.ok) throw await parseApiError(response, '載入 Community Overlay 事件失敗')
  return response.json()
}

export async function getCommunityOverlayTheme(
  publicKey: string
): Promise<CommunityOverlayPublishedTheme> {
  const response = await apiFetch(API_ENDPOINTS.communityOverlay.theme, {
    headers: { 'X-Overlay-Key': publicKey },
  })
  if (!response.ok) throw await parseApiError(response, '載入 Community Overlay 樣式失敗')
  return response.json()
}

export function getCommunityOverlaySettings(): Promise<CommunityOverlayAccess> {
  return apiJson(API_ENDPOINTS.communityOverlay.settings, authed, {
    fallback: '載入共用 Overlay 設定失敗',
  })
}

export function updateCommunityOverlaySettings(enabled: boolean): Promise<CommunityOverlayAccess> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.settings,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    },
    { fallback: '更新共用 Overlay 設定失敗' }
  )
}

export function rotateCommunityOverlayKey(): Promise<CommunityOverlayAccess> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.rotateKey,
    { method: 'POST', credentials: 'include', headers: actionHeaders },
    { fallback: '輪替 Overlay 連結失敗' }
  )
}

export function getCommunityOverlayThemeSettings(): Promise<CommunityOverlayThemeState> {
  return apiJson(API_ENDPOINTS.communityOverlay.themeSettings, authed, {
    fallback: '載入 Overlay 樣式設定失敗',
  })
}

export function updateCommunityOverlayThemeDraft(
  theme: CommunityOverlayTheme,
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themeDraft,
    {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme, expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '儲存 Overlay 樣式草稿失敗' }
  )
}

export function publishCommunityOverlayTheme(
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themePublish,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...actionHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '發布 Overlay 樣式失敗' }
  )
}

export function resetCommunityOverlayThemeDraft(
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themeResetDraft,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...actionHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '還原 Overlay 樣式草稿失敗' }
  )
}
