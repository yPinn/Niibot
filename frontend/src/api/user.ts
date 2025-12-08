// User API
import { API_ENDPOINTS } from './config'

export interface User {
  name: string
  display_name: string
  avatar: string
}

// 獲取當前使用者資訊
export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch(API_ENDPOINTS.auth.user, {
      credentials: 'include', // 包含 cookies
    })
    if (!response.ok) {
      throw new Error('Failed to fetch user info')
    }
    const data = await response.json()
    return data
  } catch (error) {
    console.error('Failed to get user info:', error)
    return null
  }
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
  } catch (error) {
    console.error('Failed to logout:', error)
    throw error
  }
}
