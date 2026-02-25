import React, { createContext, useContext, useEffect, useRef, useState } from 'react'

import { type Channel, getCurrentUser, getTwitchMonitoredChannels, type User } from '@/api'
import { apiCache } from '@/lib/apiCache'

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

  const initRef = React.useRef({
    hasLoaded: false,
    isLoading: false,
  })

  // Track initialized state in a ref so the 401 handler closure stays current
  // without needing to re-register the listener on every isInitialized change.
  const isInitializedRef = useRef(false)
  useEffect(() => {
    isInitializedRef.current = isInitialized
  }, [isInitialized])

  // Global 401 interceptor — redirect to /login when the session expires.
  // Skipped during initial auth check (not yet initialized) and on overlay
  // routes (/:username/*/overlay) so live-stream OBS views are never disrupted.
  useEffect(() => {
    const handleUnauthorized = () => {
      if (!isInitializedRef.current) return
      if (window.location.pathname.includes('/overlay')) return
      apiCache.clear()
      setUser(null)
      setChannels([])
      window.location.href = '/login'
    }
    window.addEventListener('auth:unauthorized', handleUnauthorized)
    return () => window.removeEventListener('auth:unauthorized', handleUnauthorized)
  }, [])

  const refreshUser = React.useCallback(async () => {
    try {
      const userData = await getCurrentUser({ forceRefresh: true })
      setUser(userData)
    } catch (error) {
      console.error('Failed to load user:', error)
      setUser(null)
    }
  }, [])

  const refreshChannels = React.useCallback(async () => {
    try {
      const channelData = await getTwitchMonitoredChannels({ forceRefresh: true })
      setChannels(channelData)
    } catch (error) {
      console.error('Failed to load channels:', error)
      setChannels([])
    }
  }, [])

  // Initial data load
  useEffect(() => {
    if (initRef.current.hasLoaded || initRef.current.isLoading) {
      return
    }

    initRef.current.isLoading = true
    initRef.current.hasLoaded = true

    const loadInitialData = async () => {
      try {
        const [userData, channelData] = await Promise.all([
          getCurrentUser({ forceRefresh: false }),
          getTwitchMonitoredChannels({ forceRefresh: false }),
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

  // Channels polling: 60s (bot status 已移至 ServiceStatusContext)
  useEffect(() => {
    if (!user) return
    const interval = setInterval(refreshChannels, 60_000)
    return () => clearInterval(interval)
  }, [user, refreshChannels])

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
