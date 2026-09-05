import { describe, expect, it } from 'vitest'

import { OVERLAY_POLL_INTERVAL_MS, pollingRequestsPerDay } from './overlayPolling'

describe('persistent overlay request budget', () => {
  it('keeps remaining polling overlays below 3k requests per day', () => {
    const requestsPerDay = pollingRequestsPerDay(OVERLAY_POLL_INTERVAL_MS.gameQueue)

    expect(requestsPerDay).toBe(2_880)
    expect(requestsPerDay).toBeLessThan(3_000)
  })

  it('does not expose Live Display or Video Queue polling intervals after their stream migrations', () => {
    expect(OVERLAY_POLL_INTERVAL_MS).not.toHaveProperty('liveDisplayEvents')
    expect(OVERLAY_POLL_INTERVAL_MS).not.toHaveProperty('liveDisplayThemes')
    expect(OVERLAY_POLL_INTERVAL_MS).not.toHaveProperty('videoQueue')
    expect(OVERLAY_POLL_INTERVAL_MS.gameQueue).toBeGreaterThanOrEqual(30_000)
  })
})
