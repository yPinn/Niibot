import type {
  StreamSchedule,
  StreamScheduleOccurrenceException,
  StreamScheduleSegment,
} from '@/api/streamSchedule'

const WEEKDAY_BY_SHORT_NAME: Record<string, number> = {
  Mon: 0,
  Tue: 1,
  Wed: 2,
  Thu: 3,
  Fri: 4,
  Sat: 5,
  Sun: 6,
}

interface ZonedParts {
  dateStr: string
  weekday: number
  minutes: number
}

function zonedParts(date: Date, timezone: string): ZonedParts {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const value = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find(part => part.type === type)?.value ?? ''

  return {
    dateStr: `${value('year')}-${value('month')}-${value('day')}`,
    weekday: WEEKDAY_BY_SHORT_NAME[value('weekday')] ?? 0,
    minutes: Number(value('hour')) * 60 + Number(value('minute')),
  }
}

/** A browser-timezone-independent calendar date container. */
export function calendarDate(dateStr: string): Date {
  return new Date(`${dateStr}T00:00:00Z`)
}

export function toDateStr(date: Date): string {
  const month = String(date.getUTCMonth() + 1).padStart(2, '0')
  const day = String(date.getUTCDate()).padStart(2, '0')
  return `${date.getUTCFullYear()}-${month}-${day}`
}

export function dateStrInTimeZone(date: Date, timezone: string): string {
  return zonedParts(date, timezone).dateStr
}

export function todayInTimeZone(timezone: string, now = new Date()): string {
  return dateStrInTimeZone(now, timezone)
}

export function weekdayInTimeZone(date: Date, timezone: string): number {
  return zonedParts(date, timezone).weekday
}

export function minutesInTimeZone(date: Date, timezone: string): number {
  return zonedParts(date, timezone).minutes
}

export function timeZoneOffsetLabel(timezone: string, now = new Date()): string {
  return (
    new Intl.DateTimeFormat('en-US', { timeZone: timezone, timeZoneName: 'shortOffset' })
      .formatToParts(now)
      .find(part => part.type === 'timeZoneName')?.value ?? ''
  )
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setUTCDate(next.getUTCDate() + days)
  return next
}

/** 0 = Monday, matching the backend's date.weekday() / StreamSchedule.weekday
 * convention — JS's Date.getDay() is 0 = Sunday, so this remaps it. Used for
 * matching a date against a stored recurring schedule's weekday — NOT for
 * calendar display order, which starts the week on Sunday (see startOfWeek)
 * independently of this numbering. */
export function weekdayOf(date: Date): number {
  return (date.getUTCDay() + 6) % 7
}

/** Calendar display starts the week on Sunday — a display preference,
 * unrelated to weekdayOf's backend-matching numbering above. Uses Date's
 * native getDay() (0 = Sunday) directly. */
export function startOfWeek(date: Date): Date {
  return addDays(date, -date.getUTCDay())
}

/** The Sunday on/before the 1st of the month — first cell of a month grid. */
export function startOfMonthGrid(date: Date): Date {
  const firstOfMonth = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1))
  return startOfWeek(firstOfMonth)
}

/** How many week-rows a month's grid actually needs (4–6) — a month whose
 * last day lands early in its last row doesn't need a trailing row that's
 * 100% next-month padding. */
export function monthGridWeekCount(date: Date): number {
  const gridStart = startOfMonthGrid(date)
  const lastOfMonth = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 0))
  const spanDays = Math.round((lastOfMonth.getTime() - gridStart.getTime()) / 86_400_000) + 1
  return Math.ceil(spanDays / 7)
}

export function timeStrToMinutes(hhmmss: string): number {
  const [h, m] = hhmmss.split(':').map(Number)
  return h * 60 + m
}

/** Whether a day's resolved schedule is live right now — same-day only (a
 * schedule that crosses midnight just won't get the "live" highlight on the
 * day it spills into; the day it started on still resolves and displays
 * normally). Good enough for a visual accent, not worth the extra
 * cross-midnight window math the backend resolver does for the real thing. */
export function isLiveNow(
  schedule: StreamSchedule,
  occurrenceDate: string,
  now: Date,
  timezone: string
): boolean {
  const startMinutes = timeStrToMinutes(schedule.start_time)
  const current = zonedParts(now, timezone)
  const dayDelta = Math.round(
    (calendarDate(current.dateStr).getTime() - calendarDate(occurrenceDate).getTime()) / 86_400_000
  )
  const elapsed = dayDelta * 1440 + current.minutes - startMinutes
  return elapsed >= 0 && elapsed < schedule.duration_minutes
}

/** Minutes since a specific schedule's own start, only when it's the one
 * actually airing right now (enabled, applies to today by weekday/date, and
 * within its time window) — null otherwise. Unlike isLiveNow, this checks a
 * single schedule object directly rather than "whatever resolved for a
 * date," so the caller doesn't need to have already matched it against the
 * day-level override rule themselves (e.g. the schedule-edit sheet, which
 * only ever has one schedule in hand, not the full list to resolve against). */
export function liveElapsedMinutesFor(
  schedule: StreamSchedule,
  now: Date,
  timezone: string
): number | null {
  if (!schedule.enabled) return null
  const today = dateStrInTimeZone(now, timezone)
  const yesterday = toDateStr(addDays(calendarDate(today), -1))
  const occurrenceDates =
    schedule.kind === 'one_off' ? [schedule.specific_date] : [yesterday, today]

  for (const occurrenceDate of occurrenceDates) {
    if (!occurrenceDate) continue
    const applies =
      schedule.kind === 'one_off'
        ? schedule.specific_date === occurrenceDate
        : schedule.weekday === weekdayOf(calendarDate(occurrenceDate))
    if (!applies || !isLiveNow(schedule, occurrenceDate, now, timezone)) continue
    const dayDelta = Math.round(
      (calendarDate(today).getTime() - calendarDate(occurrenceDate).getTime()) / 86_400_000
    )
    return (
      dayDelta * 1440 + minutesInTimeZone(now, timezone) - timeStrToMinutes(schedule.start_time)
    )
  }
  return null
}

/** Whether a recurring schedule already existed by a given date — a schedule
 * created this Friday for "every Monday" shouldn't retroactively backfill
 * onto this week's Monday, which already passed before it existed. Doesn't
 * apply to one-offs: their specific_date is an explicit, deliberate choice,
 * not an implicit weekly match to guard against. The real auto-apply
 * resolver (shared/services/stream_schedule_service.py) never needs this —
 * it only ever evaluates today/yesterday relative to the actual current
 * moment, so it can't reach a date before the schedule existed regardless.
 * This is purely about the calendar not showing a misleading backfill. */
function existedBy(schedule: StreamSchedule, dateStr: string, timezone: string): boolean {
  return (
    !schedule.created_at || dateStrInTimeZone(new Date(schedule.created_at), timezone) <= dateStr
  )
}

/** Resolve which schedule (if any) applies on a given date — the same
 * day-level override rule the backend's resolver uses (see
 * shared/services/stream_schedule_service.py): an enabled one-off on that
 * exact date wins outright; otherwise the enabled recurring schedule for
 * that weekday, if any. Computed client-side over the already-loaded
 * schedule list — no extra request per visible day. */
export function resolveScheduleForDate(
  schedules: StreamSchedule[],
  dateStr: string,
  timezone = 'Asia/Taipei',
  exceptions: StreamScheduleOccurrenceException[] = []
): StreamSchedule | null {
  return resolveSchedulesForDate(schedules, dateStr, timezone, exceptions)[0] ?? null
}

export function resolveSchedulesForDate(
  schedules: StreamSchedule[],
  dateStr: string,
  timezone = 'Asia/Taipei',
  exceptions: StreamScheduleOccurrenceException[] = []
): StreamSchedule[] {
  const oneOffs = schedules.filter(
    s => s.enabled && s.kind === 'one_off' && s.specific_date === dateStr
  )
  const exceptionScheduleIds = new Set(
    exceptions
      .filter(exception => exception.occurrence_date === dateStr)
      .map(exception => exception.recurring_schedule_id)
  )

  const weekday = weekdayOf(calendarDate(dateStr))
  const recurring = schedules.filter(
    s =>
      s.enabled &&
      s.kind === 'recurring' &&
      s.weekday === weekday &&
      !exceptionScheduleIds.has(s.id) &&
      existedBy(s, dateStr, timezone)
  )
  return [...oneOffs, ...recurring].sort((a, b) => a.start_time.localeCompare(b.start_time))
}

export function cancelledSchedulesForDate(
  schedules: StreamSchedule[],
  dateStr: string,
  exceptions: StreamScheduleOccurrenceException[]
): StreamSchedule[] {
  const cancelledIds = new Set(
    exceptions
      .filter(exception => exception.occurrence_date === dateStr && exception.kind === 'cancelled')
      .map(exception => exception.recurring_schedule_id)
  )
  return schedules.filter(
    schedule => schedule.kind === 'recurring' && cancelledIds.has(schedule.id)
  )
}

/** A schedule resolved for the PREVIOUS calendar day that spills past
 * midnight into this one — e.g. a schedule starting 23:00 for 3h is still
 * running at 01:00 the next day. Returns how many minutes past midnight it
 * runs, or null if there's no such overflow (covers both "no schedule
 * yesterday" and "yesterday's schedule ended before midnight"). Used by the
 * week timeline so a late-night stream doesn't just vanish at the day
 * boundary — the resolved schedule for THIS day (if any) is unaffected;
 * they're independent blocks on the same row, not a conflict to resolve. */
export function resolveContinuationForDate(
  schedules: StreamSchedule[],
  dateStr: string,
  timezone = 'Asia/Taipei',
  exceptions: StreamScheduleOccurrenceException[] = []
): { schedule: StreamSchedule; minutes: number } | null {
  const prevDateStr = toDateStr(addDays(calendarDate(dateStr), -1))
  const prev = resolveScheduleForDate(schedules, prevDateStr, timezone, exceptions)
  if (!prev) return null
  const overflowMinutes = timeStrToMinutes(prev.start_time) + prev.duration_minutes - 1440
  return overflowMinutes > 0 ? { schedule: prev, minutes: overflowMinutes } : null
}

/** Which segment is currently in effect, elapsedMinutes after the schedule's
 * own start — the same "latest offset not in the future" rule the backend's
 * real resolver uses, so a live view shows what's actually airing right now
 * instead of just the schedule's base title (segments can override it
 * mid-stream). Shared by the week timeline (per visible block) and the
 * segment editor (to mark which row is current/past while live). */
export function resolveActiveSegment(
  segments: StreamScheduleSegment[],
  elapsedMinutes: number
): StreamScheduleSegment | null {
  let active: StreamScheduleSegment | null = null
  for (const seg of segments) {
    if (
      seg.offset_minutes <= elapsedMinutes &&
      (!active || seg.offset_minutes > active.offset_minutes)
    ) {
      active = seg
    }
  }
  return active
}

/** The earliest (lowest-offset) segment — used as a block's default
 * title/category when it isn't currently live (resolveActiveSegment covers
 * the live case, where a later segment may already be in effect). */
export function firstSegment(segments: StreamScheduleSegment[]): StreamScheduleSegment | null {
  if (segments.length === 0) return null
  return segments.reduce((earliest, s) =>
    s.offset_minutes < earliest.offset_minutes ? s : earliest
  )
}
