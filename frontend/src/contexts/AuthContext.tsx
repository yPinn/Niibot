import React, { createContext, useContext, useEffect, useState } from 'react'

import { type Channel, getCurrentUser, getMonitoredChannels, type User } from '@/api'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isInitialized: boolean
  channels: Channel[]
  logout: () => void
  refreshUser: () => Promise<void>
  refreshChannels: () => Promise<void>
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [channels, setChannels] = useState<Channel[]>([])

  // 使用 ref 來追蹤是否已經初始化
  const initRef = React.useRef({
    hasLoaded: false,
    isLoading: false,
  })

  // 載入用戶資料的函數（用於手動刷新）
  const refreshUser = React.useCallback(async () => {
    try {
      const userData = await getCurrentUser({ forceRefresh: true })
      setUser(userData)
    } catch (error) {
      console.error('Failed to load user:', error)
      setUser(null)
    }
  }, [])

  // 載入頻道資料的函數（用於手動刷新）
  const refreshChannels = React.useCallback(async () => {
    try {
      const channelData = await getMonitoredChannels({ forceRefresh: true })
      setChannels(channelData)
    } catch (error) {
      console.error('Failed to load channels:', error)
      setChannels([])
    }
  }, [])

  useEffect(() => {
    // 防止重複載入
    if (initRef.current.hasLoaded || initRef.current.isLoading) {
      return
    }

    initRef.current.isLoading = true
    initRef.current.hasLoaded = true

    // 初始載入用戶和頻道資料
    const loadInitialData = async () => {
      try {
        const [userData, channelData] = await Promise.all([
          getCurrentUser({ forceRefresh: false }),
          getMonitoredChannels({ forceRefresh: false }),
        ])
        setUser(userData)
        setChannels(channelData)
      } catch (error) {
        console.error('Failed to load initial data:', error)
        setUser(null)
        setChannels([])
      } finally {
        setIsInitialized(true)
        initRef.current.isLoading = false
      }
    }

    loadInitialData()
  }, [])

  return (
    <AuthContext.Provider
      value={{
        user,
        isAuthenticated: !!user,
        isInitialized,
        channels,
        logout: () => {
          setUser(null)
          setChannels([])
        },
        refreshUser,
        refreshChannels,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
