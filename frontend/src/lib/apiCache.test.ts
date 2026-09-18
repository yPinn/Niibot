import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

const KEY = 'test-key'

beforeEach(() => {
  apiCache.clear()
})

describe('get / set', () => {
  it('returns cached data on a cache hit', () => {
    apiCache.set(KEY, { name: 'Alice' })
    expect(apiCache.get(KEY)).toEqual({ name: 'Alice' })
  })

  it('returns null on a cache miss', () => {
    expect(apiCache.get('nonexistent')).toBeNull()
  })

  it('overwrites an existing entry with set()', () => {
    apiCache.set(KEY, 'first')
    apiCache.set(KEY, 'second')
    expect(apiCache.get(KEY)).toBe('second')
  })

  it('evicts the oldest entry when the cache reaches MAX_SIZE (200)', () => {
    for (let i = 0; i < 200; i++) {
      apiCache.set(`evict-key-${i}`, `value-${i}`)
    }
    // Adding one more triggers eviction of the first inserted entry
    apiCache.set('evict-key-new', 'new-value')
    expect(apiCache.get('evict-key-0')).toBeNull()
    expect(apiCache.get('evict-key-1')).toBe('value-1')
    expect(apiCache.get('evict-key-new')).toBe('new-value')
  })
})

describe('TTL', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns null after the default TTL (5 min) expires', () => {
    apiCache.set(KEY, 'value')
    vi.advanceTimersByTime(5 * 60 * 1000 + 1)
    expect(apiCache.get(KEY)).toBeNull()
  })

  it('returns data just before the default TTL expires', () => {
    apiCache.set(KEY, 'value')
    vi.advanceTimersByTime(5 * 60 * 1000 - 100)
    expect(apiCache.get(KEY)).toBe('value')
  })

  it('respects a custom TTL passed to get()', () => {
    const CUSTOM_TTL = 1_000
    apiCache.set(KEY, 'value')
    vi.advanceTimersByTime(CUSTOM_TTL + 1)
    expect(apiCache.get(KEY, CUSTOM_TTL)).toBeNull()
  })
})

describe('delete / clear', () => {
  it('delete() removes only the specified key', () => {
    apiCache.set(KEY, 'hello')
    apiCache.set('other', 'world')
    apiCache.delete(KEY)
    expect(apiCache.get(KEY)).toBeNull()
    expect(apiCache.get('other')).toBe('world')
  })

  it('clear() removes all entries', () => {
    apiCache.set('a', 1)
    apiCache.set('b', 2)
    apiCache.clear()
    expect(apiCache.get('a')).toBeNull()
    expect(apiCache.get('b')).toBeNull()
  })
})

describe('patch', () => {
  it('updates the cached entry using the updater function', () => {
    apiCache.set(KEY, { count: 1, name: 'Alice' })
    apiCache.patch<{ count: number; name: string }>(KEY, d => ({ ...d, count: d.count + 1 }))
    expect(apiCache.get(KEY)).toEqual({ count: 2, name: 'Alice' })
  })

  it('does nothing silently when the key is absent', () => {
    expect(() => apiCache.patch('missing', (d: unknown) => d)).not.toThrow()
  })
})

describe('CACHE_KEYS', () => {
  it('STATS_CHANNEL returns keyed string', () => {
    expect(CACHE_KEYS.STATS_CHANNEL(7)).toBe('stats:channel:7')
  })

  it('ANALYTICS_SUMMARY returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_SUMMARY(30)).toBe('analytics:summary:30')
  })

  it('ANALYTICS_TOP_COMMANDS returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_TOP_COMMANDS(7, 10)).toBe('analytics:top-commands:7:10')
  })

  it('ANALYTICS_SESSION_COMMANDS returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_SESSION_COMMANDS(42)).toBe('analytics:session-commands:42')
  })

  it('ANALYTICS_SESSION_EVENTS returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_SESSION_EVENTS(42)).toBe('analytics:session-events:42')
  })

  it('ANALYTICS_INSIGHTS returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_INSIGHTS(7)).toBe('analytics:insights:7')
  })

  it('ANALYTICS_VIEWERS returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_VIEWERS(30)).toBe('analytics:viewers:30')
  })

  it('ANALYTICS_VIEWER_PROFILE returns keyed string', () => {
    expect(CACHE_KEYS.ANALYTICS_VIEWER_PROFILE('user123', 7)).toBe(
      'analytics:viewer-profile:user123:7'
    )
  })

  it('MATCHER_SUMMARIES returns keyed string', () => {
    expect(CACHE_KEYS.MATCHER_SUMMARIES(30)).toBe('matcher:summaries:30')
  })

  it('MATCHER_SELF_STATS returns keyed string', () => {
    expect(CACHE_KEYS.MATCHER_SELF_STATS(30)).toBe('matcher:self-stats:30')
  })
})

describe('fetch', () => {
  it('calls fetcher and caches the result on first call', async () => {
    const fetcher = vi.fn().mockResolvedValue('data')
    const result = await apiCache.fetch(KEY, fetcher)
    expect(result).toBe('data')
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(apiCache.get(KEY)).toBe('data')
  })

  it('returns cached result without calling fetcher again', async () => {
    const fetcher = vi.fn().mockResolvedValue('data')
    await apiCache.fetch(KEY, fetcher)
    const result = await apiCache.fetch(KEY, fetcher)
    expect(result).toBe('data')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('deduplicates concurrent requests for the same key', async () => {
    const fetcher = vi.fn().mockResolvedValue('data')
    const [p1, p2, p3] = [
      apiCache.fetch(KEY, fetcher),
      apiCache.fetch(KEY, fetcher),
      apiCache.fetch(KEY, fetcher),
    ]
    const results = await Promise.all([p1, p2, p3])
    expect(results).toEqual(['data', 'data', 'data'])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('bypasses cache when forceRefresh is true', async () => {
    await apiCache.fetch(KEY, () => Promise.resolve('stale'))
    const fetcher = vi.fn().mockResolvedValue('fresh')
    const result = await apiCache.fetch(KEY, fetcher, { forceRefresh: true })
    expect(result).toBe('fresh')
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('refetches after TTL expires', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn().mockResolvedValue('data')
    await apiCache.fetch(KEY, fetcher, { ttl: 1_000 })
    vi.advanceTimersByTime(1_001)
    await apiCache.fetch(KEY, fetcher, { ttl: 1_000 })
    expect(fetcher).toHaveBeenCalledTimes(2)
    vi.useRealTimers()
  })
})
