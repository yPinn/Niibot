import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingSpinner } from '@/components/LoadingSpinner'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/contexts/AuthContext'
import { useTenant } from '@/contexts/TenantContext'

export function ProtectedRoute() {
  const { user, isAuthenticated, isInitialized, isInitError, retryInit } = useAuth()
  const { tenants, isInitialized: isTenantInitialized } = useTenant()
  const location = useLocation()

  if (!isInitialized || (isAuthenticated && !isTenantInitialized)) {
    return <LoadingSpinner fullScreen text="Loading..." />
  }

  if (isInitError) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">無法連線到伺服器，請檢查網路後重試。</p>
        <Button onClick={retryInit}>重試</Button>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  if (!user?.is_activated && !user?.is_owner && tenants.length === 0) {
    return <Navigate to="/activate" replace />
  }

  return <Outlet />
}

export function OwnerRoute() {
  const { user, isAuthenticated, isInitialized } = useAuth()

  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="Loading..." />
  }

  if (!isAuthenticated || !user?.is_owner) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}

export function PublicOnlyRoute() {
  const { isAuthenticated, isInitialized, user } = useAuth()
  const location = useLocation()

  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="Loading..." />
  }

  if (isAuthenticated) {
    const defaultDashboard = user?.platform === 'discord' ? '/discord' : '/dashboard'
    const raw = (location.state as { from?: { pathname: string } })?.from?.pathname
    // Ensure redirect target is a relative path (prevents open redirect to //evil.com)
    const from = raw?.startsWith('/') && !raw.startsWith('//') ? raw : defaultDashboard
    return <Navigate to={from} replace />
  }

  return <Outlet />
}
