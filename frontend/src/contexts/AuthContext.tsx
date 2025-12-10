import React, { createContext, useContext, useEffect, useState } from 'react'

import { type Channel, getCurrentUser, getMonitoredChannels, type User } from '@/api'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isInitialized: boolean
  channels: Channel[]
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [channels, setChannels] = useState<Channel[]>([])
  const hasLoaded = React.useRef(false)

  useEffect(() => {
    // 防止重複載入（例如 React Strict Mode）
    if (hasLoaded.current) return
    hasLoaded.current = true

    // 載入 user
    getCurrentUser()
      .then(userData => {
        setUser(userData)
      })
      .catch(error => {
        console.error('Failed to load user:', error)
        setUser(null)
      })
      .finally(() => {
        setIsInitialized(true)
      })

    // 載入 channels
    getMonitoredChannels()
      .then(channelData => {
        setChannels(channelData)
      })
      .catch(error => {
        console.error('Failed to load channels:', error)
        setChannels([])
      })
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
