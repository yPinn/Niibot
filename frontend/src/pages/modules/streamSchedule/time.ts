// A time range is more plannable than "start + duration in minutes" — these
// helpers convert between the two, since the backend still stores
// start_time + duration_minutes (duration survives cross-midnight schedules
// cleanly; an absolute end time alone would not).

export function timeToMinutes(hhmm: string): number {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

export function minutesToTime(totalMinutes: number): string {
  const wrapped = ((totalMinutes % 1440) + 1440) % 1440
  const h = Math.floor(wrapped / 60)
  const m = wrapped % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

/** Minutes from start to end, wrapping past midnight when end <= start
 * (e.g. 23:00 → 02:00 is a 180-minute overnight stream, not negative). Note
 * end === start wraps to a full 1440 here (a schedule's own start/end can
 * legitimately mean "runs the full day") — offsetFromStart below is the
 * variant for when equal times should mean zero instead, e.g. converting a
 * segment's picked clock time back to "minutes after the schedule's start",
 * where equal-to-start means the go-live segment (offset 0), not a segment a
 * full day later. */
export function durationBetween(start: string, end: string): number {
  const diff = timeToMinutes(end) - timeToMinutes(start)
  return diff > 0 ? diff : diff + 1440
}

/** Minutes from a schedule's start to a clock time within its window —
 * unlike durationBetween, start === time means offset 0 (the go-live
 * segment), not a full-day wrap. */
export function offsetFromStart(start: string, time: string): number {
  const diff = timeToMinutes(time) - timeToMinutes(start)
  return diff >= 0 ? diff : diff + 1440
}

export function endTimeFor(start: string, durationMinutes: number): string {
  return minutesToTime(timeToMinutes(start) + durationMinutes)
}

/** True if the end time falls on the following calendar day. */
export function crossesMidnight(start: string, durationMinutes: number): boolean {
  return timeToMinutes(start) + durationMinutes > 1440
}
