import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

import { type Channel, getCurrentUser, getTwitchMonitoredChannels, type User } from '@/api'
import { logout as apiLogout } from '@/api/user'
import { apiCache } from '@/lib/apiCache'

interface AuthContextType {
  user: User | null
  isAuthenticated: boolean
  isInitialized: boolean
  isInitError: boolean // true when init failed due to a network error (not a 401)
  isAffiliate: boolean // true for Twitch affiliate or partner
  channels: Channel[]
  logout: () => Promise<void>
  refreshUser: () => Promise<void>
  refreshChannels: () => Promise<void>
  retryInit: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

/** Public paths that don't need the auth bootstrap — skip the fetch entirely. */
function isPublicPath(pathname: string): boolean {
  return (
    pathname === '/' ||
    pathname === '/terms' ||
    pathname === '/privacy' ||
    pathname === '/login' ||
    pathname.includes('/overlay') ||
    pathname.startsWith('/donate/') ||
    /^\/[^/]+\/commands$/.test(pathname)
  )
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [isInitError, setIsInitError] = useState(false)
  const [channels, setChannels] = useState<Channel[]>([])

  const initRef = React.useRef({
    hasLoaded: false,
    isLoading: false,
  })

  // Ref keeps the 401 handler closure current without re-registering on every render.
  const isInitializedRef = useRef(false)
  useEffect(() => {
    isInitializedRef.current = isInitialized
  }, [isInitialized])

  // Global 401 interceptor — skip during init and on overlay routes.
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

  const refreshUser = useCallback(async () => {
    try {
      const userData = await getCurrentUser({ forceRefresh: true })
      setUser(userData)
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to load user:', error)
      setUser(null)
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } catch (error) {
      if (import.meta.env.DEV) console.error('Logout request failed:', error)
    }
    setUser(null)
    setChannels([])
    window.location.href = '/login'
  }, [])

  const refreshChannels = useCallback(async () => {
    try {
      const channelData = await getTwitchMonitoredChannels({ forceRefresh: true })
      setChannels(channelData)
    } catch (error) {
      if (import.meta.env.DEV) console.error('Failed to load channels:', error)
      setChannels([])
    }
  }, [])

  const loadInitialData = useCallback(async () => {
    if (initRef.current.isLoading) return
    initRef.current.isLoading = true
    setIsInitError(false)

    // Public pages don't need auth data — skip the fetch entirely.
    if (isPublicPath(window.location.pathname)) {
      setIsInitialized(true)
      initRef.current.isLoading = false
      initRef.current.hasLoaded = true
      return
    }

    try {
      const [userData, channelData] = await Promise.all([
        getCurrentUser({ forceRefresh: true }),
        getTwitchMonitoredChannels({ forceRefresh: true }),
      ])
      setUser(userData)
      setChannels(channelData)
      setIsInitialized(true)
      initRef.current.hasLoaded = true
    } catch (error) {
      // Network error (not a 401 — apiFetch handles those via auth:unauthorized).
      // Don't treat a connectivity blip as "logged out".
      if (import.meta.env.DEV) console.error('Failed to load initial data:', error)
      setIsInitError(true)
      setIsInitialized(true)
    } finally {
      initRef.current.isLoading = false
    }
  }, [])

  // Initial data load — guarded by ref against StrictMode double-mount.
  useEffect(() => {
    if (initRef.current.hasLoaded || initRef.current.isLoading) return
    loadInitialData()
  }, [loadInitialData])

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
        isInitError,
        isAffiliate: user?.broadcaster_type === 'affiliate' || user?.broadcaster_type === 'partner',
        channels,
        logout,
        refreshUser,
        refreshChannels,
        retryInit: loadInitialData,
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
