import { API_ENDPOINTS } from './config'
import { apiJson } from './errors'

export interface AISettings {
  bot_name: string
  persona: string
  self_pronoun: string
  audience_reference: string
  tone_preset: 'neutral' | 'witty' | 'energetic' | 'tsundere' | 'calm'
  catchphrase: string
  catchphrase_frequency: 'off' | 'rare' | 'occasional'
  example_replies: string[]
  response_lang: 'zh-tw' | 'en' | 'auto'
  refusal_style: 'humorous' | 'polite'
  max_tokens: number
  enabled_emotes: string[]
  enabled: boolean
  memory_enabled: boolean
  cooldown: number
  min_role: 'everyone' | 'subscriber' | 'vip' | 'moderator' | 'broadcaster'
  assistant_mode: 'persona' | 'roleplay'
  active_roleplay_revision_id: number | null
}

export const AI_SETTINGS_DEFAULT: AISettings = {
  bot_name: 'Niibot',
  persona: '',
  self_pronoun: '我',
  audience_reference: '大家',
  tone_preset: 'neutral',
  catchphrase: '',
  catchphrase_frequency: 'off',
  example_replies: [],
  response_lang: 'zh-tw',
  refusal_style: 'polite',
  max_tokens: 250,
  enabled_emotes: [],
  enabled: false,
  memory_enabled: false,
  cooldown: 30,
  min_role: 'everyone',
  assistant_mode: 'persona',
  active_roleplay_revision_id: null,
}

export interface Pack {
  id: string
  name: string
  description: string
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

const tenantActionHeaders = { 'X-Niibot-Action': 'ai-settings' } as const
type EditableAISettings = Omit<AISettings, 'assistant_mode' | 'active_roleplay_revision_id'>

export function getTenantAISettings(channelId: string): Promise<AISettings> {
  return apiJson(API_ENDPOINTS.tenants.aiSettings(channelId), authed, {
    fallback: '載入 AI 設定失敗',
  })
}

export function patchTenantAISettings(
  channelId: string,
  patch: Partial<EditableAISettings>
): Promise<AISettings> {
  return apiJson(
    API_ENDPOINTS.tenants.aiSettings(channelId),
    {
      method: 'PATCH',
      ...authed,
      headers: { 'Content-Type': 'application/json', ...tenantActionHeaders },
      body: JSON.stringify(patch),
    },
    { fallback: '更新 AI 設定失敗' }
  )
}

export function resetTenantAISettings(channelId: string): Promise<AISettings> {
  return apiJson(
    API_ENDPOINTS.tenants.aiSettingsReset(channelId),
    { method: 'POST', ...authed, headers: tenantActionHeaders },
    { fallback: '重設 AI 設定失敗' }
  )
}
