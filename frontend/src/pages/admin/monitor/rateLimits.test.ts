import { describe, expect, it } from 'vitest'

import type { CloudflareUsage, RateLimitSnapshot } from '@/api/admin'

import {
  cloudflareRatio,
  cloudflareSeverity,
  formatWindow,
  rankByPressure,
  severity,
  usageRatio,
  worstSeverity,
} from './rateLimits'

const NOW = 1_800_000_000

function snap(overrides: Partial<RateLimitSnapshot> = {}): RateLimitSnapshot {
  return {
    name: 'x',
    group: 'inbound',
    limit: 10,
    window_seconds: 60,
    used: 0,
    keys: 0,
    ...overrides,
  }
}

describe('usageRatio', () => {
  it('uses the busiest key against the limit', () => {
    expect(usageRatio(snap({ used: 3, keys: 2 }))).toBe(0.3)
  })

  it('prefers the provider-reported budget', () => {
    expect(
      usageRatio(snap({ used: 1, provider: { limit: 800, remaining: 200, reset_at: null } }))
    ).toBe(0.75)
  })

  it('is full while throttled and unknown without a cap', () => {
    expect(usageRatio(snap({ limit: null, limited: true }))).toBe(1)
    expect(usageRatio(snap({ limit: null }))).toBeNull()
  })
})

describe('severity', () => {
  it('is idle with nothing in the window', () => {
    expect(severity(snap(), NOW)).toBe('idle')
  })

  it('is hot near the limit, while blocked, or while throttled', () => {
    expect(severity(snap({ used: 9, keys: 1 }), NOW)).toBe('hot')
    expect(severity(snap({ blocked_seconds: 3 }), NOW)).toBe('hot')
    expect(severity(snap({ limit: null, limited: true }), NOW)).toBe('hot')
  })

  it('warns on a recent rejection, a queue, or heavy use', () => {
    expect(severity(snap({ rejected: 1, last_rejected_at: NOW - 60 }), NOW)).toBe('warn')
    expect(severity(snap({ queued: 2 }), NOW)).toBe('warn')
    expect(severity(snap({ used: 6, keys: 1 }), NOW)).toBe('warn')
  })

  it('lets an old rejection fade to ok', () => {
    expect(
      severity(snap({ used: 1, keys: 1, rejected: 1, last_rejected_at: NOW - 3600 }), NOW)
    ).toBe('ok')
  })
})

describe('ranking', () => {
  it('orders by severity, then share used, then name', () => {
    const ranked = rankByPressure(
      [
        snap({ name: 'b', used: 1, keys: 1 }),
        snap({ name: 'hot', used: 10, keys: 1 }),
        snap({ name: 'a', used: 1, keys: 1 }),
        snap({ name: 'c', used: 2, keys: 1 }),
      ],
      NOW
    )
    expect(ranked.map(s => s.name)).toEqual(['hot', 'c', 'a', 'b'])
  })

  it('reports the worst severity of a list', () => {
    expect(worstSeverity([], NOW)).toBe('idle')
    expect(worstSeverity([snap(), snap({ queued: 1 })], NOW)).toBe('warn')
  })
})

describe('formatWindow', () => {
  it.each([
    [30, '30s'],
    [60, '1m'],
    [1800, '30m'],
    [3600, '1h'],
    [null, ''],
  ])('%s → %s', (input, expected) => {
    expect(formatWindow(input)).toBe(expected)
  })
})

describe('cloudflare', () => {
  const base: CloudflareUsage = {
    configured: true,
    limit: 100_000,
    day_start: null,
    reset_at: null,
    workers_requests: null,
    pages_requests: null,
    total_requests: 65_000,
    errors: [],
    fetched_at: null,
  }

  it('maps the daily total to a ratio and severity', () => {
    expect(cloudflareRatio(base)).toBe(0.65)
    expect(cloudflareSeverity(base)).toBe('warn')
  })

  it('is idle when unconfigured or unknown', () => {
    expect(cloudflareSeverity({ ...base, configured: false })).toBe('idle')
    expect(cloudflareRatio({ ...base, total_requests: null })).toBeNull()
  })
})
