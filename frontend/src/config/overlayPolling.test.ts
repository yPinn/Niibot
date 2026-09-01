import { describe, expect, it } from 'vitest'

import { OVERLAY_POLL_INTERVAL_MS, pollingRequestsPerDay } from './overlayPolling'

describe('persistent overlay request budget', () => {
  it('keeps remaining polling overlays below 12k requests per day', () => {
    const requestsPerDay =
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.videoQueue) +
      pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.gameQueue)

    expect(requestsPerDay).toBe(11_520)
    expect(requestsPerDay).toBeLessThan(12_000)
  })

  it('does not expose Live Display polling intervals after the stream migration', () => {
    expect(OVERLAY_POLL_INTERVAL_MS).not.toHaveProperty('liveDisplayEvents')
    expect(OVERLAY_POLL_INTERVAL_MS).not.toHaveProperty('liveDisplayThemes')
    expect(OVERLAY_POLL_INTERVAL_MS.videoQueue).toBeGreaterThanOrEqual(10_000)
    expect(OVERLAY_POLL_INTERVAL_MS.gameQueue).toBeGreaterThanOrEqual(30_000)
  })
})
