import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface AISettings {
  bot_name: string
  persona: string
  self_pronoun: string
  catchphrase: string
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
  self_pronoun: '我',
  catchphrase: '',
  response_lang: 'zh-tw',
  refusal_style: 'humorous',
  max_tokens: 250,
  enabled_emotes: [],
  enabled: false,
  cooldown: 15,
  min_role: 'everyone',
}

export interface Pack {
  id: string
  name: string
  description: string
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

const authed = { credentials: 'include' } as const

export function getAIPacks(): Promise<Pack[]> {
  return apiJson(API_ENDPOINTS.ai.packs, authed, { fallback: '載入 AI 知識包失敗' })
}

export function getAISettings(): Promise<AISettings> {
  return apiJson(API_ENDPOINTS.ai.settings, authed, { fallback: '載入 AI 設定失敗' })
}

export function patchAISettings(patch: Partial<AISettings>): Promise<AISettings> {
  return apiJson(
    API_ENDPOINTS.ai.settings,
    {
      method: 'PATCH',
      ...authed,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    },
    { fallback: '更新 AI 設定失敗' }
  )
}

export function resetAISettings(): Promise<AISettings> {
  return apiJson(
    API_ENDPOINTS.ai.reset,
    { method: 'POST', ...authed },
    { fallback: '重設 AI 設定失敗' }
  )
}

export function getAIEmotes(): Promise<EmoteItem[]> {
  return apiJson(API_ENDPOINTS.ai.emotes, authed, { fallback: '載入表情符號失敗' })
}
