import { describe, expect, it } from 'vitest'

import { OVERLAY_POLL_INTERVAL_MS, pollingRequestsPerDay } from './overlayPolling'

describe('persistent overlay request budget', () => {
  it('keeps one always-on source of each overlay below 40k requests per day', () => {
    const requestsPerDay =
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.liveDisplayEvents) +
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.liveDisplayThemes) * 2 +
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.videoQueue) +
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.gameQueue)

    expect(requestsPerDay).toBe(31_680)
    expect(requestsPerDay).toBeLessThan(40_000)
  })

  it('keeps event latency bounded while moving low-frequency state out of the hot path', () => {
    expect(OVERLAY_POLL_INTERVAL_MS.liveDisplayEvents).toBeLessThanOrEqual(5_000)
    expect(OVERLAY_POLL_INTERVAL_MS.liveDisplayThemes).toBeGreaterThanOrEqual(60_000)
    expect(OVERLAY_POLL_INTERVAL_MS.videoQueue).toBeGreaterThanOrEqual(10_000)
    expect(OVERLAY_POLL_INTERVAL_MS.gameQueue).toBeGreaterThanOrEqual(30_000)
  })
})
