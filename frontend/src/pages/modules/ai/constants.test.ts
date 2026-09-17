import { describe, expect, it } from 'vitest'

import { CATCHPHRASE_FREQUENCY_OPTIONS, PERSONA_PRESETS, TONE_OPTIONS } from './constants'

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
      '預設',
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
      expect(preset.values.catchphrase).toBe('')
    }
  })
})
