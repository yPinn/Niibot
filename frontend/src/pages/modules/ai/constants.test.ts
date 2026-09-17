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
})
