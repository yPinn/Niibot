import { API_ENDPOINTS, apiFetch } from './config'

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

export async function getPublicCrosshairs(
  username: string,
  game?: CrosshairGame
): Promise<PublicCrosshairsData> {
  const base = API_ENDPOINTS.crosshairs.public(username)
  const url = game ? `${base}?game=${encodeURIComponent(game)}` : base
  const res = await apiFetch(url)
  if (!res.ok) throw new Error(`Failed to fetch crosshairs: ${res.statusText}`)
  return res.json()
}

export async function getAllPublicCrosshairs(
  game?: CrosshairGame
): Promise<CrosshairWithChannel[]> {
  const base = API_ENDPOINTS.crosshairs.allPublic
  const url = game ? `${base}?game=${encodeURIComponent(game)}` : base
  const res = await apiFetch(url)
  if (!res.ok) throw new Error(`Failed to fetch crosshairs: ${res.statusText}`)
  return res.json()
}

export async function getCrosshairs(game?: CrosshairGame): Promise<Crosshair[]> {
  const base = API_ENDPOINTS.crosshairs.list
  const url = game ? `${base}?game=${encodeURIComponent(game)}` : base
  const res = await apiFetch(url, { credentials: 'include' })
  if (!res.ok) throw new Error(`Failed to fetch crosshairs: ${res.statusText}`)
  return res.json()
}

export async function createCrosshair(data: CrosshairCreate): Promise<Crosshair> {
  const res = await apiFetch(API_ENDPOINTS.crosshairs.create, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to create crosshair: ${res.statusText}`)
  return res.json()
}

export async function updateCrosshair(id: string, data: CrosshairUpdate): Promise<Crosshair> {
  const res = await apiFetch(API_ENDPOINTS.crosshairs.update(id), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`Failed to update crosshair: ${res.statusText}`)
  return res.json()
}

export async function deleteCrosshair(id: string): Promise<void> {
  const res = await apiFetch(API_ENDPOINTS.crosshairs.delete(id), {
    method: 'DELETE',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`Failed to delete crosshair: ${res.statusText}`)
}
