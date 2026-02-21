import { Route, Routes } from 'react-router-dom'

import SidebarLayout from '@/components/layouts/SidebarLayout'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui'
import { AuthProvider } from '@/contexts/AuthContext'
import { BotProvider } from '@/contexts/BotContext'
import { ServiceStatusProvider } from '@/contexts/ServiceStatusContext'
import Commands from '@/pages/dashboard/Commands'
import Events from '@/pages/dashboard/Events'
import Overview from '@/pages/dashboard/Overview'
import SystemStatus from '@/pages/dashboard/SystemStatus'
import DiscordDashboard from '@/pages/discord/Dashboard'
import GameQueueOverlay from '@/pages/GameQueueOverlay'
import Landing from '@/pages/Landing'
import LoginPage from '@/pages/Login'
import GameQueue from '@/pages/modules/GameQueue'
import Timers from '@/pages/modules/Timers'
import NotFound from '@/pages/NotFound'
import PublicCommands from '@/pages/PublicCommands'
import Settings from '@/pages/Settings'
import TypographyDemo from '@/pages/TypographyDemo'

function App() {
  return (
    <AuthProvider>
      <ThemeProvider storageKey="vite-ui-theme">
        <ServiceStatusProvider>
          <BotProvider>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/:username/commands" element={<PublicCommands />} />
              <Route path="/:username/game-queue/overlay" element={<GameQueueOverlay />} />
              <Route path="/dev/typography" element={<TypographyDemo />} />
              <Route element={<PublicOnlyRoute />}>
                <Route path="/login" element={<LoginPage />} />
              </Route>
              <Route element={<ProtectedRoute />}>
                <Route element={<SidebarLayout />}>
                  {/* Twitch Bot Routes */}
                  <Route path="/dashboard" element={<Overview />} />
                  <Route path="/commands" element={<Commands />} />
                  <Route path="/events" element={<Events />} />
                  <Route path="/system" element={<SystemStatus />} />
                  <Route path="/settings" element={<Settings />} />
                  {/* Module Routes */}
                  <Route path="/timers" element={<Timers />} />
                  <Route path="/modules/game-queue" element={<GameQueue />} />
                  {/* Discord Bot Routes */}
                  <Route path="/discord/dashboard" element={<DiscordDashboard />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Route>
            </Routes>
            <Toaster position="bottom-right" richColors />
          </BotProvider>
        </ServiceStatusProvider>
      </ThemeProvider>
    </AuthProvider>
  )
}

export default App
