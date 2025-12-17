import { Navigate, Outlet, useLocation } from 'react-router-dom'

import { LoadingSpinner } from '@/components/LoadingSpinner'
import { useAuth } from '@/contexts/AuthContext'

/**
 * Protected Route Component
 * 保護需要登入才能訪問的路由
 */
export function ProtectedRoute() {
  const { isAuthenticated, isInitialized } = useAuth()
  const location = useLocation()

  // 等待初始化完成，避免誤判未登入而重定向
  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="載入中..." />
  }

  if (!isAuthenticated) {
    // 未登入，重定向到登入頁面，保存原本要去的位置
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  // 已登入，渲染子路由
  return <Outlet />
}

/**
 * Public Only Route Component
 * 只允許未登入用戶訪問（如登入頁面）
 */
export function PublicOnlyRoute() {
  const { isAuthenticated, isInitialized } = useAuth()
  const location = useLocation()

  // 等待初始化完成
  if (!isInitialized) {
    return <LoadingSpinner fullScreen text="載入中..." />
  }

  if (isAuthenticated) {
    // 已登入，重定向到原本要去的位置，或 dashboard
    const from = (location.state as { from?: { pathname: string } })?.from?.pathname || '/dashboard'
    return <Navigate to={from} replace />
  }

  // 未登入，渲染子路由（登入頁面）
  return <Outlet />
}
