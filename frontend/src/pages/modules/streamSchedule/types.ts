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
  { mode: 'create'; prefill?: CreatePrefill } | { mode: 'edit'; schedule: StreamSchedule }
