// User API
import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS } from './config'

export interface User {
  name: string
  display_name: string
  avatar: string
}

// 內部函數：實際的 API 調用
async function fetchCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(API_ENDPOINTS.auth.user, {
      credentials: 'include', // 包含 cookies
    })

    if (!response.ok) {
      return null
    }

    const data = await response.json()
    return data
  } catch (error) {
    console.error('Failed to get user info:', error)
    return null
  }
}

// 獲取當前使用者資訊（帶快取）
export async function getCurrentUser(options?: { forceRefresh?: boolean }): Promise<User | null> {
  return apiCache.fetch(CACHE_KEYS.CURRENT_USER, fetchCurrentUser, {
    ttl: 5 * 60 * 1000, // 5 分鐘
    forceRefresh: options?.forceRefresh,
  })
}

// 登出
export async function logout(): Promise<void> {
  try {
    const response = await fetch(API_ENDPOINTS.auth.logout, {
      method: 'POST',
      credentials: 'include', // 包含 cookies
    })
    if (!response.ok) {
      throw new Error('Failed to logout')
    }
    // 清除所有快取
    apiCache.clear()
  } catch (error) {
    console.error('Failed to logout:', error)
    throw error
  }
}
