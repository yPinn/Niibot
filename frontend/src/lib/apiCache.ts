/**
 * 簡單的 API 快取機制
 * 避免在頁面切換時重複調用相同的 API
 */

interface CacheEntry<T> {
  data: T
  timestamp: number
}

class ApiCache {
  private cache: Map<string, CacheEntry<unknown>> = new Map()
  private defaultTTL = 5 * 60 * 1000 // 預設 5 分鐘
  private pendingRequests: Map<string, Promise<unknown>> = new Map() // 防止並發請求
  private storageKey = '__niibot_api_cache__'

  constructor() {
    // 從 sessionStorage 恢復快取
    this.loadFromStorage()
  }

  /**
   * 從 sessionStorage 載入快取
   */
  private loadFromStorage(): void {
    try {
      const stored = sessionStorage.getItem(this.storageKey)
      if (stored) {
        const data = JSON.parse(stored)
        this.cache = new Map(Object.entries(data))
      }
    } catch {
      // 靜默失敗，不影響功能
    }
  }

  /**
   * 保存快取到 sessionStorage
   */
  private saveToStorage(): void {
    try {
      const data = Object.fromEntries(this.cache.entries())
      sessionStorage.setItem(this.storageKey, JSON.stringify(data))
    } catch {
      // 靜默失敗，不影響功能
    }
  }

  /**
   * 從快取中取得資料，如果過期則回傳 null
   */
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

  /**
   * 將資料存入快取
   */
  set<T>(key: string, data: T): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
    })
    this.saveToStorage()
  }

  /**
   * 清除指定 key 的快取
   */
  delete(key: string): void {
    this.cache.delete(key)
    this.saveToStorage()
  }

  /**
   * 清除所有快取
   */
  clear(): void {
    this.cache.clear()
    sessionStorage.removeItem(this.storageKey)
  }

  /**
   * 包裝 API 調用，自動處理快取和防止並發請求
   */
  async fetch<T>(
    key: string,
    fetcher: () => Promise<T>,
    options?: { ttl?: number; forceRefresh?: boolean }
  ): Promise<T> {
    // 如果不強制刷新，先檢查快取
    if (!options?.forceRefresh) {
      const cached = this.get<T>(key, options?.ttl)
      if (cached !== null) {
        return cached
      }
    }

    // 檢查是否有正在進行的請求
    const pending = this.pendingRequests.get(key) as Promise<T> | undefined
    if (pending) {
      return pending
    }

    // 調用 API 並存入快取
    const promise = fetcher()
      .then(data => {
        this.set(key, data)
        return data
      })
      .finally(() => {
        // 請求完成後移除 pending 狀態
        this.pendingRequests.delete(key)
      })

    // 儲存 pending promise
    this.pendingRequests.set(key, promise)
    return promise
  }
}

// 導出單例
export const apiCache = new ApiCache()

// 快取鍵常數
export const CACHE_KEYS = {
  CURRENT_USER: 'auth:current-user',
  CHANNELS: 'channels:list',
} as const
