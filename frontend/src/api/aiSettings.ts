import { API_ENDPOINTS, apiFetch } from './config'

export interface AISettings {
  bot_name: string
  persona: string
  response_lang: 'zh-tw' | 'en' | 'auto'
  refusal_style: 'humorous' | 'polite'
  max_tokens: number
  enabled_emotes: string[]
  enabled: boolean
  cooldown: number
  min_role: 'everyone' | 'subscriber' | 'vip' | 'moderator' | 'broadcaster'
}

export const AI_SETTINGS_DEFAULT: AISettings = {
  bot_name: 'Niibot',
  persona: '',
  response_lang: 'zh-tw',
  refusal_style: 'humorous',
  max_tokens: 250,
  enabled_emotes: [],
  enabled: false,
  cooldown: 15,
  min_role: 'everyone',
}

export interface EmoteItem {
  id: string
  name: string
  url: string
  emote_type: string
  tier: string
  available: boolean
  animated: boolean
}

export async function getAISettings(): Promise<AISettings> {
  const res = await apiFetch(API_ENDPOINTS.ai.settings, { credentials: 'include' })
  if (!res.ok) throw new Error(`Failed to fetch AI settings: ${res.status}`)
  return res.json()
}

export async function patchAISettings(patch: Partial<AISettings>): Promise<AISettings> {
  const res = await apiFetch(API_ENDPOINTS.ai.settings, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  if (!res.ok) throw new Error(`Failed to update AI settings: ${res.status}`)
  return res.json()
}

export async function resetAISettings(): Promise<AISettings> {
  const res = await apiFetch(API_ENDPOINTS.ai.reset, {
    method: 'POST',
    credentials: 'include',
  })
  if (!res.ok) throw new Error(`Failed to reset AI settings: ${res.status}`)
  return res.json()
}

export async function getAIEmotes(): Promise<EmoteItem[]> {
  const res = await apiFetch(API_ENDPOINTS.ai.emotes, { credentials: 'include' })
  if (!res.ok) throw new Error(`Failed to fetch emotes: ${res.status}`)
  return res.json()
}
