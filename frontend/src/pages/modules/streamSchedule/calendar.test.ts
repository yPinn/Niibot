import { describe, expect, it } from 'vitest'

import type { StreamSchedule } from '@/api/streamSchedule'

import {
  addDays,
  isLiveNow,
  monthGridWeekCount,
  resolveContinuationForDate,
  resolveScheduleForDate,
  startOfMonthGrid,
  startOfWeek,
  timeStrToMinutes,
  toDateStr,
  weekdayOf,
} from './calendar'

function schedule(overrides: Partial<StreamSchedule>): StreamSchedule {
  return {
    id: 1,
    channel_id: 'chan1',
    kind: 'recurring',
    weekday: 0,
    specific_date: null,
    start_time: '20:00:00',
    duration_minutes: 180,
    title_template: '',
    enabled: true,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

describe('weekdayOf', () => {
  it('maps Monday to 0 and Sunday to 6 (backend convention, not JS getDay())', () => {
    expect(weekdayOf(new Date('2026-09-21T00:00:00'))).toBe(0) // Monday
    expect(weekdayOf(new Date('2026-09-27T00:00:00'))).toBe(6) // Sunday
  })
})

describe('startOfWeek / startOfMonthGrid', () => {
  it('starts the week on Sunday', () => {
    // 2026-09-24 is a Thursday, so the Sunday on/before it is 2026-09-20.
    expect(toDateStr(startOfWeek(new Date('2026-09-24T00:00:00')))).toBe('2026-09-20')
  })

  it('starts the month grid on the Sunday on/before the 1st', () => {
    // 2026-10-01 is a Thursday, so the Sunday on/before it is 2026-09-27.
    expect(toDateStr(startOfMonthGrid(new Date('2026-10-15T00:00:00')))).toBe('2026-09-27')
  })
})

describe('monthGridWeekCount', () => {
  it('needs only 5 weeks when the month ends early in its last calendar-grid row', () => {
    // September 2026: 1st is a Tuesday, 30th is a Wednesday — grid starts
    // Sun 8/30 and the 30th falls in the 5th row, no 6th row needed.
    expect(monthGridWeekCount(new Date('2026-09-15T00:00:00'))).toBe(5)
  })

  it('needs 6 weeks when the month spills into a 6th row', () => {
    // August 2026: 1st is a Saturday, so the grid starts Sun 7/26 and the
    // 31st (a Monday) lands in the 6th row.
    expect(monthGridWeekCount(new Date('2026-08-15T00:00:00'))).toBe(6)
  })
})

describe('timeStrToMinutes', () => {
  it('parses HH:MM:SS into minutes since midnight', () => {
    expect(timeStrToMinutes('20:30:00')).toBe(20 * 60 + 30)
  })
})

describe('isLiveNow', () => {
  const today = toDateStr(new Date())

  it('is true when now falls inside the schedule window on the same day', () => {
    const now = new Date()
    const startMinutes = now.getHours() * 60 + now.getMinutes() - 10
    const s = schedule({
      start_time: `${String(Math.floor(startMinutes / 60)).padStart(2, '0')}:${String(startMinutes % 60).padStart(2, '0')}:00`,
      duration_minutes: 60,
    })
    expect(isLiveNow(s, today, now)).toBe(true)
  })

  it('is false for a different day even if the time-of-day would match', () => {
    const now = new Date()
    const s = schedule({ start_time: '00:00:00', duration_minutes: 1440 })
    expect(isLiveNow(s, '2000-01-01', now)).toBe(false)
  })

  it('is false once the window has ended', () => {
    const now = new Date()
    const startMinutes = (now.getHours() * 60 + now.getMinutes() - 120 + 1440) % 1440
    const s = schedule({
      start_time: `${String(Math.floor(startMinutes / 60)).padStart(2, '0')}:${String(startMinutes % 60).padStart(2, '0')}:00`,
      duration_minutes: 30,
    })
    expect(isLiveNow(s, today, now)).toBe(false)
  })
})

describe('resolveContinuationForDate', () => {
  it("is null when yesterday's schedule ends before midnight", () => {
    const s = schedule({ id: 1, weekday: 0, start_time: '20:00:00', duration_minutes: 180 }) // Monday 20:00–23:00
    expect(resolveContinuationForDate([s], '2026-09-22')).toBeNull() // Tuesday
  })

  it("returns the overflow minutes when yesterday's schedule crosses midnight", () => {
    // Monday 23:00 for 180 minutes ends Tuesday 02:00 — 120 minutes past midnight.
    const s = schedule({ id: 1, weekday: 0, start_time: '23:00:00', duration_minutes: 180 })
    const result = resolveContinuationForDate([s], '2026-09-22') // Tuesday
    expect(result?.schedule.id).toBe(1)
    expect(result?.minutes).toBe(120)
  })

  it('is null when there is no schedule the day before', () => {
    const s = schedule({ id: 1, weekday: 1, start_time: '23:00:00', duration_minutes: 180 }) // Tuesday
    expect(resolveContinuationForDate([s], '2026-09-22')).toBeNull() // Tuesday itself, not the day after
  })
})

describe('addDays', () => {
  it('adds days without mutating the input', () => {
    const start = new Date('2026-09-21T00:00:00')
    const next = addDays(start, 3)
    expect(toDateStr(next)).toBe('2026-09-24')
    expect(toDateStr(start)).toBe('2026-09-21')
  })
})

describe('resolveScheduleForDate', () => {
  it('resolves a recurring schedule by weekday', () => {
    const recurring = schedule({ id: 1, weekday: 0 }) // Monday
    const result = resolveScheduleForDate([recurring], '2026-09-21')
    expect(result?.id).toBe(1)
  })

  it('one-off on the exact date wins over a recurring schedule for that weekday', () => {
    const recurring = schedule({ id: 1, kind: 'recurring', weekday: 0 })
    const oneOff = schedule({
      id: 2,
      kind: 'one_off',
      weekday: null,
      specific_date: '2026-09-21',
    })
    const result = resolveScheduleForDate([recurring, oneOff], '2026-09-21')
    expect(result?.id).toBe(2)
  })

  it('a disabled schedule never resolves', () => {
    const disabled = schedule({ id: 1, weekday: 0, enabled: false })
    expect(resolveScheduleForDate([disabled], '2026-09-21')).toBeNull()
  })

  it('returns null for a day with no matching schedule', () => {
    const tuesday = schedule({ id: 1, weekday: 1 })
    expect(resolveScheduleForDate([tuesday], '2026-09-21')).toBeNull() // 2026-09-21 is Monday
  })
})
