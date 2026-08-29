import { describe, expect, it } from 'vitest'

import { renderTemplate } from './renderTemplate'

describe('renderTemplate', () => {
  it('substitutes known placeholders', () => {
    expect(renderTemplate('感謝 $(user) $(tier)', { user: 'A', tier: 'T2' })).toBe('感謝 A T2')
  })

  it('leaves unknown placeholders as-is', () => {
    expect(renderTemplate('$(user) $(missing)', { user: 'A' })).toBe('A $(missing)')
  })

  it('does not rescan a substituted value (no injection)', () => {
    expect(renderTemplate('$(message) $(user)', { message: '$(user)', user: 'X' })).toBe(
      '$(user) X'
    )
  })

  it('treats $ sequences in a value literally', () => {
    expect(renderTemplate('$(m)', { m: '$& $1 $$' })).toBe('$& $1 $$')
  })

  it('returns the template unchanged when it has no placeholders', () => {
    expect(renderTemplate('just text', { user: 'A' })).toBe('just text')
  })
})
