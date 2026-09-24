import type { ScheduleKind, StreamSchedule } from '@/api/streamSchedule'

/** Prefills a fresh create — e.g. clicking an empty day in the calendar view
 * starts a one-off for that date instead of the plain defaults. */
export interface CreatePrefill {
  kind?: ScheduleKind
  weekday?: number
  specificDate?: string
}

// Create no longer pins a kind up front — the sheet has a single entry point
// and the recurring-vs-one-off choice happens inside it, driven by which
// time option (weekday vs. specific date) the user picks.
export type EditingState =
  | { mode: 'create'; prefill?: CreatePrefill }
  // calendarDate is only set when opened by clicking a specific day on the
  // calendar (not from the plain schedule table, which has no date context)
  // — it's what lets the sheet offer "skip just this day" for a recurring
  // schedule's specific occurrence.
  | { mode: 'edit'; schedule: StreamSchedule; calendarDate?: string }
