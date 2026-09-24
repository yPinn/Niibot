import type { ScheduleKind } from '@/api/streamSchedule'

// 0 = Monday, matching the backend's date.weekday() convention.
export const WEEKDAY_LABELS = ['週一', '週二', '週三', '週四', '週五', '週六', '週日']

/** Indices into WEEKDAY_LABELS in Sunday-first display order — calendar
 * views and weekday pickers render in this order, while the underlying
 * `weekday` value stored on a schedule keeps its backend Monday=0 numbering
 * regardless of how it's displayed. */
export const WEEK_DISPLAY_ORDER = [6, 0, 1, 2, 3, 4, 5]

export const TITLE_VARS = [{ var: '$(channel)', desc: '頻道名稱' }]

/** One color per schedule kind, shared by the month-grid chip and the week
 * timeline block so a schedule looks the same wherever it appears. The
 * recurring fill (`bg-secondary`) sits very close in lightness to the
 * surrounding card/background in dark mode, so a matching border is what
 * actually keeps the block legible rather than blending into its background —
 * not just a decorative touch. */
export function scheduleBlockClass(kind: ScheduleKind): string {
  return kind === 'one_off'
    ? 'bg-primary/15 text-primary border border-primary/30'
    : 'bg-secondary text-secondary-foreground border border-secondary-foreground/20'
}
