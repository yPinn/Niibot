const DAY_MS = 24 * 60 * 60 * 1_000

export const OVERLAY_POLL_INTERVAL_MS = {
  videoQueue: 10_000,
  gameQueue: 30_000,
} as const

export function pollingRequestsPerDay(intervalMs: number): number {
  return DAY_MS / intervalMs
}
