import { Route, Routes } from 'react-router-dom'

import SidebarLayout from '@/components/layouts/SidebarLayout'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { ThemeProvider } from '@/components/theme-provider'
import { AuthProvider } from '@/contexts/AuthContext'
import About from '@/pages/About'
import Dashboard from '@/pages/Dashboard'
import LoginPage from '@/pages/login'
import NotFound from '@/pages/NotFound'

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <AuthProvider>
        <Routes>
          <Route path="/" element={<About />} />

          {/* 只允許未登入用戶訪問 */}
          <Route element={<PublicOnlyRoute />}>
            <Route path="/login" element={<LoginPage />} />
          </Route>

          {/* 需要登入才能訪問 */}
          <Route element={<ProtectedRoute />}>
            <Route element={<SidebarLayout />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="*" element={<NotFound />} />
            </Route>
          </Route>
        </Routes>
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
