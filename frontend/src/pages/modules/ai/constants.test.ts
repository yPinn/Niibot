import { describe, expect, it } from 'vitest'

import { AI_SETTINGS_DEFAULT } from '@/api/aiSettings'

import {
  CATCHPHRASE_FREQUENCY_OPTIONS,
  LANG_OPTIONS,
  PERSONA_PRESETS,
  REFUSAL_OPTIONS,
  ROLE_OPTIONS,
  TONE_OPTIONS,
} from './constants'

describe('AI persona presets', () => {
  it('use only supported structured persona values', () => {
    const tones = new Set(TONE_OPTIONS.map(option => option.value))
    const frequencies = new Set(CATCHPHRASE_FREQUENCY_OPTIONS.map(option => option.value))

    for (const preset of PERSONA_PRESETS) {
      expect(tones.has(preset.values.tone_preset)).toBe(true)
      expect(frequencies.has(preset.values.catchphrase_frequency)).toBe(true)
      expect(preset.values.example_replies.length).toBeLessThanOrEqual(3)
      expect(preset.values.example_replies.every(reply => reply.length <= 120)).toBe(true)
    }
  })

  it('defaults to restrained character signals for short Twitch replies', () => {
    expect(PERSONA_PRESETS.map(preset => preset.name)).toEqual([
      '自然助手',
      '機智吐槽',
      '元氣',
      '傲嬌',
      '穩重',
    ])

    for (const preset of PERSONA_PRESETS) {
      expect(preset.values.persona).not.toMatch(/每個問題|每句|絕不|總是|習慣/)
      expect(preset.values.catchphrase_frequency).not.toBe('occasional')
      expect(preset.values.example_replies.length).toBeLessThanOrEqual(1)
      expect(preset.values.self_pronoun).toBe('我')
      expect(preset.values).not.toHaveProperty('audience_reference')
      expect(preset.values).not.toHaveProperty('refusal_style')
      expect(preset.values.catchphrase).toBe('')
    }
  })

  it('uses conservative factory defaults for free-model operation', () => {
    expect(AI_SETTINGS_DEFAULT.catchphrase_frequency).toBe('off')
    expect(AI_SETTINGS_DEFAULT.refusal_style).toBe('polite')
    expect(AI_SETTINGS_DEFAULT.cooldown).toBe(30)
  })

  it('names options by their visible result', () => {
    expect(LANG_OPTIONS.map(option => option.label)).toEqual(['繁體中文', '英文', '跟隨提問'])
    expect(REFUSAL_OPTIONS.map(option => option.label)).toEqual(['清楚婉拒', '輕鬆婉拒'])
    expect(TONE_OPTIONS.map(option => option.label)).toEqual([
      '自然中性',
      '機智吐槽',
      '明快元氣',
      '輕微傲嬌',
      '沉穩簡潔',
    ])
    expect(CATCHPHRASE_FREQUENCY_OPTIONS.map(option => option.label)).toEqual([
      '不使用',
      '偶爾',
      '較常',
    ])
    expect(ROLE_OPTIONS.map(option => option.label)).toEqual([
      '所有觀眾',
      '訂閱者以上',
      'VIP 以上',
      '版主以上',
      '僅頻道主',
    ])
  })
})
