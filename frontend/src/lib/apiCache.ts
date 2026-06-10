// API cache with TTL and request deduplication.
// Intentionally in-memory only — sessionStorage would cause stale data after
// page refresh (same tab shares sessionStorage, new tab gets a fresh one).
interface CacheEntry<T> {
  data: T
  timestamp: number
}

const MAX_SIZE = 200

class ApiCache {
  private cache: Map<string, CacheEntry<unknown>> = new Map()
  private defaultTTL = 5 * 60 * 1000
  private pendingRequests: Map<string, Promise<unknown>> = new Map()

  get<T>(key: string, ttl?: number): T | null {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined
    if (!entry) return null

    const age = Date.now() - entry.timestamp
    const maxAge = ttl ?? this.defaultTTL

    if (age > maxAge) {
      this.cache.delete(key)
      return null
    }

    return entry.data
  }

  set<T>(key: string, data: T): void {
    if (this.cache.size >= MAX_SIZE && !this.cache.has(key)) {
      // Evict the oldest entry (Map insertion order = LRU approximation)
      this.cache.delete(this.cache.keys().next().value!)
    }
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
    })
  }

  patch<T>(key: string, updater: (data: T) => T): void {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined
    if (!entry) return
    this.cache.set(key, { data: updater(entry.data), timestamp: Date.now() })
  }

  delete(key: string): void {
    this.cache.delete(key)
  }

  clear(): void {
    this.cache.clear()
  }

  async fetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { ttl?: number; forceRefresh?: boolean }
  ): Promise<T> {
    if (!options?.forceRefresh) {
      const cached = this.get<T>(key, options?.ttl)
      if (cached !== null) {
        return cached
      }
    }

    const pending = this.pendingRequests.get(key) as Promise<T> | undefined
    if (pending && !options?.forceRefresh) {
      return pending
    }

    const promise = fetcher()
      .then(data => {
        this.set(key, data)
        return data
      })
      .finally(() => {
        this.pendingRequests.delete(key)
      })

    this.pendingRequests.set(key, promise)
    return promise
  }
}

export const apiCache = new ApiCache()

export const CACHE_KEYS = {
  CURRENT_USER: 'auth:current-user',
  CHANNELS: 'channels:list',
  STATS_CHANNEL: (days: number) => `stats:channel:${days}`,
  ANALYTICS_SUMMARY: (days: number) => `analytics:summary:${days}`,
  ANALYTICS_TOP_COMMANDS: (days: number, limit: number) =>
    `analytics:top-commands:${days}:${limit}`,
  ANALYTICS_SESSION_COMMANDS: (sessionId: number) => `analytics:session-commands:${sessionId}`,
  ANALYTICS_SESSION_EVENTS: (sessionId: number) => `analytics:session-events:${sessionId}`,
  ANALYTICS_INSIGHTS: (days: number) => `analytics:insights:${days}`,
  ANALYTICS_VIEWERS: (days: number) => `analytics:viewers:${days}`,
  ANALYTICS_VIEWER_PROFILE: (userId: string, days: number) =>
    `analytics:viewer-profile:${userId}:${days}`,
  ANALYTICS_CHANNEL_BADGES: 'analytics:channel-badges',
  ANALYTICS_GLOBAL_BADGES: 'analytics:global-badges',
  MATCHER_SUMMARIES: (days: number) => `matcher:summaries:${days}`,
  MATCHER_VIEWERS: (partnerChannelId: string, limit: number, offset: number) =>
    `matcher:viewers:${partnerChannelId}:${limit}:${offset}`,
} as const
