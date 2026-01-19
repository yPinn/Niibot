import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingSpinner } from '@/components/LoadingSpinner'
import { useAuth } from '@/contexts/AuthContext'

/**
 * Protected route - requires authentication
 */
export function ProtectedRoute() {
  const { isAuthenticated, isInitialized } = useAuth()
  const location = useLocation()

  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="Loading..." />
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
    const from =
      (location.state as { from?: { pathname: string } })?.from?.pathname || defaultDashboard
    return <Navigate to={from} replace />
  }

  return <Outlet />
}
