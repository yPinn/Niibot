import type { StreamSchedule } from '@/api/streamSchedule'

// Local-date (not UTC) helpers — a UTC-based ISO string can land on the wrong
// calendar day for the user, especially right around midnight.

export function toDateStr(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${date.getFullYear()}-${month}-${day}`
}

export function todayLocalDate(): string {
  return toDateStr(new Date())
}

export function addDays(date: Date, days: number): Date {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}

/** 0 = Monday, matching the backend's date.weekday() / StreamSchedule.weekday
 * convention — JS's Date.getDay() is 0 = Sunday, so this remaps it. Used for
 * matching a date against a stored recurring schedule's weekday — NOT for
 * calendar display order, which starts the week on Sunday (see startOfWeek)
 * independently of this numbering. */
export function weekdayOf(date: Date): number {
  return (date.getDay() + 6) % 7
}

/** Calendar display starts the week on Sunday — a display preference,
 * unrelated to weekdayOf's backend-matching numbering above. Uses Date's
 * native getDay() (0 = Sunday) directly. */
export function startOfWeek(date: Date): Date {
  return addDays(date, -date.getDay())
}

/** The Sunday on/before the 1st of the month — first cell of a month grid. */
export function startOfMonthGrid(date: Date): Date {
  const firstOfMonth = new Date(date.getFullYear(), date.getMonth(), 1)
  return startOfWeek(firstOfMonth)
}

/** How many week-rows a month's grid actually needs (4–6) — a month whose
 * last day lands early in its last row doesn't need a trailing row that's
 * 100% next-month padding. */
export function monthGridWeekCount(date: Date): number {
  const gridStart = startOfMonthGrid(date)
  const lastOfMonth = new Date(date.getFullYear(), date.getMonth() + 1, 0)
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
export function isLiveNow(schedule: StreamSchedule, dateStr: string, now: Date): boolean {
  if (dateStr !== toDateStr(now)) return false
  const startMinutes = timeStrToMinutes(schedule.start_time)
  const nowMinutes = now.getHours() * 60 + now.getMinutes()
  return nowMinutes >= startMinutes && nowMinutes < startMinutes + schedule.duration_minutes
}

/** Minutes since a specific schedule's own start, only when it's the one
 * actually airing right now (enabled, applies to today by weekday/date, and
 * within its time window) — null otherwise. Unlike isLiveNow, this checks a
 * single schedule object directly rather than "whatever resolved for a
 * date," so the caller doesn't need to have already matched it against the
 * day-level override rule themselves (e.g. the schedule-edit sheet, which
 * only ever has one schedule in hand, not the full list to resolve against). */
export function liveElapsedMinutesFor(schedule: StreamSchedule, now: Date): number | null {
  if (!schedule.enabled) return null
  const today = toDateStr(now)
  const appliesToday =
    schedule.kind === 'one_off'
      ? schedule.specific_date === today
      : schedule.weekday === weekdayOf(now)
  if (!appliesToday || !isLiveNow(schedule, today, now)) return null
  return now.getHours() * 60 + now.getMinutes() - timeStrToMinutes(schedule.start_time)
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
function existedBy(schedule: StreamSchedule, dateStr: string): boolean {
  return !schedule.created_at || toDateStr(new Date(schedule.created_at)) <= dateStr
}

/** Resolve which schedule (if any) applies on a given date — the same
 * day-level override rule the backend's resolver uses (see
 * shared/services/stream_schedule_service.py): an enabled one-off on that
 * exact date wins outright; otherwise the enabled recurring schedule for
 * that weekday, if any. Computed client-side over the already-loaded
 * schedule list — no extra request per visible day. */
export function resolveScheduleForDate(
  schedules: StreamSchedule[],
  dateStr: string
): StreamSchedule | null {
  const oneOffs = schedules
    .filter(s => s.enabled && s.kind === 'one_off' && s.specific_date === dateStr)
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
  if (oneOffs.length > 0) return oneOffs[0]

  const weekday = weekdayOf(new Date(`${dateStr}T00:00:00`))
  const recurring = schedules
    .filter(
      s => s.enabled && s.kind === 'recurring' && s.weekday === weekday && existedBy(s, dateStr)
    )
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
  return recurring[0] ?? null
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
  dateStr: string
): { schedule: StreamSchedule; minutes: number } | null {
  const prevDateStr = toDateStr(addDays(new Date(`${dateStr}T00:00:00`), -1))
  const prev = resolveScheduleForDate(schedules, prevDateStr)
  if (!prev) return null
  const overflowMinutes = timeStrToMinutes(prev.start_time) + prev.duration_minutes - 1440
  return overflowMinutes > 0 ? { schedule: prev, minutes: overflowMinutes } : null
}
