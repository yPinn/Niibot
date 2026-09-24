import { describe, expect, it } from 'vitest'

import { crossesMidnight, durationBetween, endTimeFor, minutesToTime, timeToMinutes } from './time'

describe('timeToMinutes / minutesToTime', () => {
  it('round-trips a normal time', () => {
    expect(timeToMinutes('20:30')).toBe(20 * 60 + 30)
    expect(minutesToTime(20 * 60 + 30)).toBe('20:30')
  })

  it('wraps minutesToTime past 24h back into 00:00-23:59', () => {
    expect(minutesToTime(25 * 60)).toBe('01:00')
  })
})

describe('durationBetween', () => {
  it('computes a same-day range', () => {
    expect(durationBetween('20:00', '23:00')).toBe(180)
  })

  it('wraps past midnight when end <= start', () => {
    expect(durationBetween('23:00', '02:00')).toBe(180)
  })

  it('treats an identical start/end as a full 24h loop, not zero', () => {
    expect(durationBetween('20:00', '20:00')).toBe(1440)
  })
})

describe('endTimeFor', () => {
  it('adds duration to start, wrapping past midnight', () => {
    expect(endTimeFor('23:00', 180)).toBe('02:00')
    expect(endTimeFor('20:00', 180)).toBe('23:00')
  })
})

describe('crossesMidnight', () => {
  it('is true only when the window spills into the next calendar day', () => {
    expect(crossesMidnight('20:00', 180)).toBe(false)
    expect(crossesMidnight('23:00', 180)).toBe(true)
  })
})
