import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { getTenants, type Tenant } from '@/api/tenants'
import { useAuth } from '@/contexts/AuthContext'
import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

interface TenantContextValue {
  tenants: Tenant[]
  activeTenant: Tenant | null
  isInitialized: boolean
  isLoading: boolean
  error: Error | null
  refreshTenants: () => Promise<void>
  selectTenant: (channelId: string) => void
}

const TenantContext = createContext<TenantContextValue | undefined>(undefined)

function tenantIdFromPath(pathname: string): string | null {
  const match = pathname.match(/^\/dashboard\/([^/]+)/)
  return match ? decodeURIComponent(match[1]) : null
}

export function TenantProvider({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isInitialized: isAuthInitialized, user } = useAuth()
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [selectedTenantId, setSelectedTenantId] = useState<string | null>(null)
  const [isInitialized, setIsInitialized] = useState(false)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<Error | null>(null)

  const refreshTenants = useCallback(async () => {
    if (!isAuthenticated || !user) {
      setTenants([])
      setSelectedTenantId(null)
      setError(null)
      setIsInitialized(true)
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      const next = await getTenants({ forceRefresh: true })
      setTenants(next)
      setSelectedTenantId(current => {
        const requested = tenantIdFromPath(window.location.pathname)
        if (requested && next.some(tenant => tenant.channel_id === requested)) return requested
        if (current && next.some(tenant => tenant.channel_id === current)) return current
        return next[0]?.channel_id ?? null
      })
    } catch (caught) {
      setTenants([])
      setSelectedTenantId(null)
      setError(caught instanceof Error ? caught : new Error('載入可管理頻道失敗'))
    } finally {
      setIsLoading(false)
      setIsInitialized(true)
    }
  }, [isAuthenticated, user])

  useEffect(() => {
    if (!isAuthInitialized) return
    const timeoutId = window.setTimeout(() => void refreshTenants(), 0)
    return () => window.clearTimeout(timeoutId)
  }, [isAuthInitialized, refreshTenants])

  useEffect(() => {
    const handleAccessRevoked = () => {
      apiCache.delete(CACHE_KEYS.TENANTS)
      void refreshTenants()
    }
    window.addEventListener('tenant:access-revoked', handleAccessRevoked)
    return () => window.removeEventListener('tenant:access-revoked', handleAccessRevoked)
  }, [refreshTenants])

  const selectTenant = useCallback(
    (channelId: string) => {
      if (tenants.some(tenant => tenant.channel_id === channelId)) {
        setSelectedTenantId(channelId)
      }
    },
    [tenants]
  )

  const activeTenant = useMemo(
    () => tenants.find(tenant => tenant.channel_id === selectedTenantId) ?? null,
    [selectedTenantId, tenants]
  )

  const value = useMemo<TenantContextValue>(
    () => ({
      tenants,
      activeTenant,
      isInitialized,
      isLoading,
      error,
      refreshTenants,
      selectTenant,
    }),
    [tenants, activeTenant, isInitialized, isLoading, error, refreshTenants, selectTenant]
  )

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>
}

export function useTenant(): TenantContextValue {
  const context = useContext(TenantContext)
  if (!context) throw new Error('useTenant must be used within TenantProvider')
  return context
}
