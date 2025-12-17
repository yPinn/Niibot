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

  // 載入用戶資料的函數
  const loadUserData = React.useCallback(async (forceRefresh = false) => {
    try {
      const userData = await getCurrentUser({ forceRefresh })
      setUser(userData)
    } catch (error) {
      console.error('Failed to load user:', error)
      setUser(null)
    }
  }, [])

  // 載入頻道資料的函數
  const loadChannelsData = React.useCallback(async (forceRefresh = false) => {
    try {
      const channelData = await getMonitoredChannels({ forceRefresh })
      setChannels(channelData)
    } catch (error) {
      console.error('Failed to load channels:', error)
      setChannels([])
    }
  }, [])

  useEffect(() => {
    // 防止重複載入
    if (initRef.current.hasLoaded || initRef.current.isLoading) {
      // 如果已經載入過，立即設置為已初始化
      if (!isInitialized && initRef.current.hasLoaded) {
        setIsInitialized(true)
      }
      return
    }

    initRef.current.isLoading = true
    initRef.current.hasLoaded = true

    // 並行載入用戶和頻道資料
    Promise.all([loadUserData(false), loadChannelsData(false)]).finally(() => {
      setIsInitialized(true)
      initRef.current.isLoading = false
    })
  }, [loadUserData, loadChannelsData, isInitialized])

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
        refreshUser: () => loadUserData(true),
        refreshChannels: () => loadChannelsData(true),
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
