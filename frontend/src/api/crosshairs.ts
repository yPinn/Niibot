import { API_ENDPOINTS, apiFetch } from './config'
import { apiJson } from './errors'

export type CrosshairGame = 'valorant'

export const CROSSHAIR_GAME_LABELS: Record<CrosshairGame, string> = {
  valorant: 'Valorant',
}

export interface Crosshair {
  id: string
  channel_id: string
  game: CrosshairGame
  name: string
  code: string
  description: string | null
  display_order: number
  copy_count: number
  created_at: string
  updated_at: string
}

export interface PublicChannelProfile {
  display_name: string | null
  profile_image_url: string | null
}

export interface CrosshairWithChannel extends Crosshair {
  channel_name: string
}

export interface PublicCrosshairsData {
  channel: PublicChannelProfile
  crosshairs: Crosshair[]
}

export interface CrosshairCreate {
  game: CrosshairGame
  name: string
  code: string
  description?: string | null
  display_order?: number
}

export interface CrosshairUpdate {
  game?: CrosshairGame
  name?: string
  code?: string
  description?: string | null
  display_order?: number
}

const withGame = (base: string, game?: CrosshairGame) =>
  game ? `${base}?game=${encodeURIComponent(game)}` : base

export function getPublicCrosshairs(
  username: string,
  game?: CrosshairGame
): Promise<PublicCrosshairsData> {
  return apiJson(withGame(API_ENDPOINTS.crosshairs.public(username), game), undefined, {
    fallback: '載入準心失敗',
  })
}

export function getAllPublicCrosshairs(game?: CrosshairGame): Promise<CrosshairWithChannel[]> {
  return apiJson(withGame(API_ENDPOINTS.crosshairs.allPublic, game), undefined, {
    fallback: '載入準心失敗',
  })
}

export function getCrosshairs(game?: CrosshairGame): Promise<Crosshair[]> {
  return apiJson(
    withGame(API_ENDPOINTS.crosshairs.list, game),
    { credentials: 'include' },
    { fallback: '載入準心失敗' }
  )
}

export function createCrosshair(data: CrosshairCreate): Promise<Crosshair> {
  return apiJson(
    API_ENDPOINTS.crosshairs.create,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '新增準心失敗' }
  )
}

export function updateCrosshair(id: string, data: CrosshairUpdate): Promise<Crosshair> {
  return apiJson(
    API_ENDPOINTS.crosshairs.update(id),
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify(data),
    },
    { fallback: '更新準心失敗' }
  )
}

export async function recordCrosshairCopy(id: string): Promise<void> {
  // fire-and-forget analytics ping — never surfaces to the user
  await apiFetch(API_ENDPOINTS.crosshairs.copy(id), { method: 'POST' }).catch(() => {})
}

export function deleteCrosshair(id: string): Promise<void> {
  return apiJson(
    API_ENDPOINTS.crosshairs.delete(id),
    { method: 'DELETE', credentials: 'include' },
    { fallback: '刪除準心失敗' }
  )
}
