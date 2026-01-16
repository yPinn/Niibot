import { Route, Routes } from 'react-router-dom'

import SidebarLayout from '@/components/layouts/SidebarLayout'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { ThemeProvider } from '@/components/theme-provider'
import { AuthProvider } from '@/contexts/AuthContext'
import { BotProvider } from '@/contexts/BotContext'
import About from '@/pages/About'
import Commands from '@/pages/Commands'
import Dashboard from '@/pages/Dashboard'
import DiscordDashboard from '@/pages/discord/Dashboard'
import Events from '@/pages/Events'
import LoginPage from '@/pages/Login'
import NotFound from '@/pages/NotFound'
import SystemStatus from '@/pages/SystemStatus'

function App() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <AuthProvider>
        <BotProvider>
          <Routes>
            <Route path="/" element={<About />} />
            <Route element={<PublicOnlyRoute />}>
              <Route path="/login" element={<LoginPage />} />
            </Route>
            <Route element={<ProtectedRoute />}>
              <Route element={<SidebarLayout />}>
                {/* Twitch Bot Routes */}
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/commands" element={<Commands />} />
                <Route path="/events" element={<Events />} />
                <Route path="/system" element={<SystemStatus />} />
                {/* Discord Bot Routes */}
                <Route path="/discord/dashboard" element={<DiscordDashboard />} />
                <Route path="*" element={<NotFound />} />
              </Route>
            </Route>
          </Routes>
        </BotProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}

export default App
