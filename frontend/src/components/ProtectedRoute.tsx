import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingSpinner } from '@/components/LoadingSpinner'
import { useAuth } from '@/contexts/AuthContext'

/**
 * Protected route - requires authentication
 */
export function ProtectedRoute() {
  const { isAuthenticated, isInitialized, isInitError, retryInit } = useAuth()
  const location = useLocation()

  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="Loading..." />
  }

  if (isInitError) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <p className="text-muted-foreground">無法連線到伺服器，請檢查網路後重試。</p>
        <button
          onClick={retryInit}
          className="rounded bg-primary px-4 py-2 text-sm text-primary-foreground hover:opacity-90"
        >
          重試
        </button>
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}

/**
 * Public only route - redirects authenticated users
 */
export function PublicOnlyRoute() {
  const { isAuthenticated, isInitialized, user } = useAuth()
  const location = useLocation()

  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="Loading..." />
  }

  if (isAuthenticated) {
    const defaultDashboard = user?.platform === 'discord' ? '/discord/dashboard' : '/dashboard'
    const raw = (location.state as { from?: { pathname: string } })?.from?.pathname
    // Ensure redirect target is a relative path (prevents open redirect to //evil.com)
    const from = raw?.startsWith('/') && !raw.startsWith('//') ? raw : defaultDashboard
    return <Navigate to={from} replace />
  }

  return <Outlet />
}
