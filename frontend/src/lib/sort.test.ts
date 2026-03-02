import { describe, expect, it } from 'vitest'

import { nameSort, ROLE_ORDER } from '@/lib/sort'

describe('nameSort', () => {
  it('sorts ASCII (English) names alphabetically', () => {
    const arr = ['zebra', 'apple', 'mango']
    expect([...arr].sort(nameSort)).toEqual(['apple', 'mango', 'zebra'])
  })

  it('places ASCII names before CJK names', () => {
    expect(nameSort('abc', '台灣')).toBeLessThan(0)
    expect(nameSort('台灣', 'abc')).toBeGreaterThan(0)
  })

  it('strips leading ! prefix before comparison', () => {
    // '!ban' vs 'abc' → 'ban' vs 'abc': 'b' > 'a' → ban > abc
    expect(nameSort('!ban', 'abc')).toBeGreaterThan(0)
    expect(nameSort('abc', '!ban')).toBeLessThan(0)
  })

  it('sorts two !-prefixed names by stripped content', () => {
    const arr = ['!zoo', '!ant']
    expect([...arr].sort(nameSort)).toEqual(['!ant', '!zoo'])
  })

  it('returns 0 for identical names', () => {
    expect(nameSort('hello', 'hello')).toBe(0)
  })

  it('returns 0 for two names that differ only by the ! prefix (same base)', () => {
    // '!hello' vs 'hello' → both strip to 'hello' → equal
    expect(nameSort('!hello', 'hello')).toBe(0)
  })
})

describe('ROLE_ORDER', () => {
  it('defines strictly increasing privilege levels', () => {
    expect(ROLE_ORDER.everyone).toBeLessThan(ROLE_ORDER.subscriber)
    expect(ROLE_ORDER.subscriber).toBeLessThan(ROLE_ORDER.vip)
    expect(ROLE_ORDER.vip).toBeLessThan(ROLE_ORDER.moderator)
    expect(ROLE_ORDER.moderator).toBeLessThan(ROLE_ORDER.broadcaster)
  })

  it('everyone starts at 0', () => {
    expect(ROLE_ORDER.everyone).toBe(0)
  })

  it('broadcaster is the highest role', () => {
    expect(ROLE_ORDER.broadcaster).toBe(4)
  })
})
