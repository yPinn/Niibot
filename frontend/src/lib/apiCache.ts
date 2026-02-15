// API cache with TTL and request deduplication
interface CacheEntry<T> {
  data: T
  timestamp: number
}

class ApiCache {
  private cache: Map<string, CacheEntry<unknown>> = new Map()
  private defaultTTL = 5 * 60 * 1000
  private pendingRequests: Map<string, Promise<unknown>> = new Map()
  private storageKey = '__niibot_api_cache__'

  constructor() {
    this.loadFromStorage()
  }

  private loadFromStorage(): void {
    try {
      const stored = sessionStorage.getItem(this.storageKey)
      if (stored) {
        const data = JSON.parse(stored)
        this.cache = new Map(Object.entries(data))
      }
    } catch {
      // Ignore storage errors
    }
  }

  private saveToStorage(): void {
    try {
      const data = Object.fromEntries(this.cache.entries())
      sessionStorage.setItem(this.storageKey, JSON.stringify(data))
    } catch {
      // Ignore storage errors
    }
  }

  get<T>(key: string, ttl?: number): T | null {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined
    if (!entry) return null

    const age = Date.now() - entry.timestamp
    const maxAge = ttl ?? this.defaultTTL

    if (age > maxAge) {
      this.cache.delete(key)
      this.saveToStorage()
      return null
    }

    return entry.data
  }

  set<T>(key: string, data: T): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
    })
    this.saveToStorage()
  }

  patch<T>(key: string, updater: (data: T) => T): void {
    const entry = this.cache.get(key) as CacheEntry<T> | undefined
    if (!entry) return
    entry.data = updater(entry.data)
    entry.timestamp = Date.now()
    this.saveToStorage()
  }

  delete(key: string): void {
    this.cache.delete(key)
    this.saveToStorage()
  }

  clear(): void {
    this.cache.clear()
    sessionStorage.removeItem(this.storageKey)
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
    if (pending) {
      return pending
    }

    const promise = fetcher()
      .then(data => {
        // Don't cache empty arrays - they might be temporary failures
        const isEmpty = Array.isArray(data) && data.length === 0
        if (!isEmpty) {
          this.set(key, data)
        }
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
} as const
