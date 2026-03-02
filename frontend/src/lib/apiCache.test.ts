import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiCache } from '@/lib/apiCache'

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
