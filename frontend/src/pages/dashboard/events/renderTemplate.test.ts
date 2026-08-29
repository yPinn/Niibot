import { describe, expect, it } from 'vitest'

import { renderTemplate } from './renderTemplate'

describe('renderTemplate', () => {
  it('substitutes known placeholders', () => {
    expect(renderTemplate('感謝 $(user) $(tier)', { user: 'A', tier: 'T2' })).toBe('感謝 A T2')
  })

  it('leaves unknown placeholders as-is', () => {
    expect(renderTemplate('$(user) $(missing)', { user: 'A' })).toBe('A $(missing)')
  })

  it('resolves a $(@name) key', () => {
    expect(renderTemplate('感謝 $(@user)！', { user: '小明', '@user': '@小明' })).toBe(
      '感謝 @小明！'
    )
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

describe('renderTemplate — optional [[ ]] segments', () => {
  const TMPL = '感謝 $(user) 訂閱滿 $(total) 個月[[，已連續 $(streak) 個月]][[（$(source)）]]！'

  it('drops segments whose vars are empty', () => {
    expect(renderTemplate(TMPL, { user: 'A', total: '14', streak: '', source: '' })).toBe(
      '感謝 A 訂閱滿 14 個月！'
    )
  })

  it('keeps a segment when its var has a value', () => {
    expect(renderTemplate(TMPL, { user: 'A', total: '14', streak: '6', source: '' })).toBe(
      '感謝 A 訂閱滿 14 個月，已連續 6 個月！'
    )
  })

  it('keeps multiple segments independently', () => {
    expect(renderTemplate(TMPL, { user: 'A', total: '3', streak: '3', source: '贈訂' })).toBe(
      '感謝 A 訂閱滿 3 個月，已連續 3 個月（贈訂）！'
    )
  })

  it('treats a missing key as absent', () => {
    expect(renderTemplate('x[[ $(y)]]', {})).toBe('x')
  })

  it('ignores [[ ]] that arrives from a substituted value', () => {
    expect(renderTemplate('$(message)', { message: '[[$(x)]]', x: 'boom' })).toBe('[[$(x)]]')
  })
})
