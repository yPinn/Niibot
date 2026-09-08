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

export interface CheckinCollectionArtworkSnapshot {
  portrait_url: string | null
  square_url: string | null
  backdrop_url: string | null
}

export interface CheckinCollectionSnapshot {
  draw_id: number
  pool_revision_id: number
  algorithm_version: string
  card: {
    id: number
    revision_id: number
    key: string
    number: string
    name: string
    artwork: CheckinCollectionArtworkSnapshot
  }
  set: {
    id: number
    key: string
    name: string
  }
  rarity: {
    key: string
    label: string
    rank: number
    effect_intensity: number
  }
  is_new: boolean
  copy_count: number
  progress: {
    owned_copies: number
    unique_cards: number
    total_cards: number
  }
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
  placement: 'bottom-left',
  radius_px: 24,
  display_ms: 5_000,
  motion: 'standard',
}

export const DEFAULT_TAROT_OVERLAY_THEME: CommunityOverlayTheme = {
  ...DEFAULT_COMMUNITY_OVERLAY_THEME,
  radius_px: 16,
  display_ms: 5_000,
}

export interface CommunityOverlayPublishedTheme<TTheme = CommunityOverlayTheme> {
  revision_id: number | null
  renderer: string
  schema_version: number
  theme: TTheme
  created_at: string | null
}

export interface CommunityOverlayThemeState<TTheme = CommunityOverlayTheme> {
  block_type: CommunityOverlayContentType
  renderer: string
  schema_version: number
  draft_version: number
  draft: TTheme
  published: CommunityOverlayPublishedTheme<TTheme>
  has_unpublished_changes: boolean
  updated_at: string
}

export type CommunityOverlayContentType = 'checkin' | 'tarot'

export interface CommunityOverlayPreviewResult {
  content_type: CommunityOverlayContentType
  event_id: number
}

const authed = { credentials: 'include' } as const
const actionHeaders = { 'X-Niibot-Action': 'live-display' } as const

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
  if (!response.ok) throw await parseApiError(response, '載入 Live Display 事件失敗')
  return response.json()
}

export async function getCommunityOverlayTheme(
  publicKey: string,
  blockType: CommunityOverlayContentType
): Promise<CommunityOverlayPublishedTheme> {
  const params = new URLSearchParams({ block_type: blockType })
  const response = await apiFetch(`${API_ENDPOINTS.communityOverlay.theme}?${params.toString()}`, {
    headers: { 'X-Overlay-Key': publicKey },
  })
  if (!response.ok) throw await parseApiError(response, '載入 Live Display 樣式失敗')
  return response.json()
}

export function getCommunityOverlaySettings(): Promise<CommunityOverlayAccess> {
  return apiJson(API_ENDPOINTS.communityOverlay.settings, authed, {
    fallback: '載入 Live Display 設定失敗',
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
    { fallback: '更新 Live Display 設定失敗' }
  )
}

export function rotateCommunityOverlayKey(): Promise<CommunityOverlayAccess> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.rotateKey,
    { method: 'POST', credentials: 'include', headers: actionHeaders },
    { fallback: '更新 OBS 顯示連結失敗' }
  )
}

export function triggerCommunityOverlayPreview(
  contentType: CommunityOverlayContentType
): Promise<CommunityOverlayPreviewResult> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.preview,
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...actionHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ content_type: contentType }),
    },
    { fallback: '測試動畫送出失敗' }
  )
}

export function getCommunityOverlayThemeSettings(
  blockType: CommunityOverlayContentType
): Promise<CommunityOverlayThemeState> {
  return apiJson(API_ENDPOINTS.communityOverlay.themeSettings(blockType), authed, {
    fallback: '載入卡片樣式設定失敗',
  })
}

export function updateCommunityOverlayThemeDraft(
  blockType: CommunityOverlayContentType,
  theme: CommunityOverlayTheme,
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themeDraft(blockType),
    {
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme, expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '儲存卡片樣式草稿失敗' }
  )
}

export function publishCommunityOverlayTheme(
  blockType: CommunityOverlayContentType,
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themePublish(blockType),
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...actionHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '套用卡片樣式失敗' }
  )
}

export function resetCommunityOverlayThemeDraft(
  blockType: CommunityOverlayContentType,
  expectedDraftVersion: number
): Promise<CommunityOverlayThemeState> {
  return apiJson(
    API_ENDPOINTS.communityOverlay.themeResetDraft(blockType),
    {
      method: 'POST',
      credentials: 'include',
      headers: { ...actionHeaders, 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_draft_version: expectedDraftVersion }),
    },
    { fallback: '還原卡片樣式草稿失敗' }
  )
}
