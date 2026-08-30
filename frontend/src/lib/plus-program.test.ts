import { describe, expect, it } from 'vitest'

import { plusProgress, subsToClose } from './plus-program'

describe('plusProgress', () => {
  it('is 50/50 below 100 points, counting toward the first threshold', () => {
    const p = plusProgress(40)
    expect(p.split).toBe('50/50')
    expect(p.nextSplit).toBe('60/40')
    expect(p.nextThreshold).toBe(100)
    expect(p.remaining).toBe(60)
  })

  it('crosses to 60/40 at exactly 100', () => {
    const p = plusProgress(100)
    expect(p.split).toBe('60/40')
    expect(p.nextSplit).toBe('70/30')
    expect(p.nextThreshold).toBe(300)
    expect(p.remaining).toBe(200)
  })

  it('is 60/40 between 100 and 300', () => {
    const p = plusProgress(200)
    expect(p.split).toBe('60/40')
    expect(p.remaining).toBe(100)
  })

  it('caps at 70/30 from 300 up', () => {
    const p = plusProgress(305)
    expect(p.split).toBe('70/30')
    expect(p.nextSplit).toBeNull()
    expect(p.nextThreshold).toBeNull()
    expect(p.remaining).toBe(0)
  })

  it('clamps negative input to zero', () => {
    expect(plusProgress(-5).remaining).toBe(100)
  })
})

describe('subsToClose', () => {
  it('converts a point gap into subs per tier, rounding up', () => {
    expect(subsToClose(45)).toEqual({ t1: 45, t2: 23, t3: 8 })
  })

  it('is all zeros at the threshold', () => {
    expect(subsToClose(0)).toEqual({ t1: 0, t2: 0, t3: 0 })
  })

  it('clamps negatives', () => {
    expect(subsToClose(-10).t1).toBe(0)
  })
})
