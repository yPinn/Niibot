// User API

export interface User {
  name: string
  display_name: string
  avatar: string
}

// 獲取當前使用者資訊
export async function getCurrentUser(): Promise<User | null> {
  try {
    const response = await fetch('/api/auth/user')
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
