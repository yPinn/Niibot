import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ErrorBoundary'
import SidebarLayout from '@/components/layouts/SidebarLayout'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { OwnerRoute, ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui'
import { AuthProvider } from '@/contexts/AuthContext'
import { BotProvider } from '@/contexts/BotContext'
import { ServiceStatusProvider } from '@/contexts/ServiceStatusContext'
// Lazy-loaded: all pages including Landing and NotFound to keep motion out of main bundle
const Landing = lazy(() => import('@/pages/Landing'))
const NotFound = lazy(() => import('@/pages/NotFound'))
const Commands = lazy(() => import('@/pages/dashboard/commands'))
const Events = lazy(() => import('@/pages/dashboard/Events'))
const Overview = lazy(() => import('@/pages/dashboard/Overview'))
const Timers = lazy(() => import('@/pages/dashboard/Timers'))
const AdminPage = lazy(() => import('@/pages/admin'))
const AdminSystemStatus = lazy(() => import('@/pages/admin/SystemStatus'))
const AdminActivationCodes = lazy(() => import('@/pages/admin/ActivationCodes'))
const Insights = lazy(() => import('@/pages/analytics/Insights'))
const DiscordDashboard = lazy(() => import('@/pages/discord/Dashboard'))
const GameQueueOverlay = lazy(() => import('@/pages/GameQueueOverlay'))
const LoginPage = lazy(() => import('@/pages/Login'))
const ChatOverlayModule = lazy(() => import('@/pages/modules/ChatOverlay'))
const GameQueue = lazy(() => import('@/pages/modules/GameQueue'))
const VideoQueue = lazy(() => import('@/pages/modules/VideoQueue'))
const CrosshairModule = lazy(() => import('@/pages/modules/crosshairs'))
const CrosshairRepo = lazy(() => import('@/pages/crosshairs'))
const PublicCommands = lazy(() => import('@/pages/PublicCommands'))
const DonatePage = lazy(() => import('@/pages/DonatePage'))
const GetStarted = lazy(() => import('@/pages/docs/GetStarted'))
const Terms = lazy(() => import('@/pages/Terms'))
const Privacy = lazy(() => import('@/pages/Privacy'))
const Settings = lazy(() => import('@/pages/Settings'))
const VideoQueueOverlay = lazy(() => import('@/pages/VideoQueueOverlay'))
const ActivatePage = lazy(() => import('@/pages/activate'))

// Dev-only: excluded from production bundle via dead-code elimination
const TypographyDemo = import.meta.env.DEV ? lazy(() => import('@/pages/TypographyDemo')) : null

function App() {
  return (
    <AuthProvider>
      <ThemeProvider storageKey="vite-ui-theme">
        <ServiceStatusProvider>
          <BotProvider>
            <ErrorBoundary>
              {/*
               * Outer Suspense: spinner for all lazy routes (login, dashboard, etc.)
               * Overlay routes override with fallback={null} via their own inner Suspense
               * so OBS browser sources see a transparent frame while the chunk loads.
               */}
              <Suspense fallback={<LoadingSpinner fullScreen />}>
                <Routes>
                  <Route path="/" element={<Landing />} />
                  <Route path="/terms" element={<Terms />} />
                  <Route path="/privacy" element={<Privacy />} />
                  <Route path="/:username/commands" element={<PublicCommands />} />
                  <Route path="/:username/crosshairs" element={<CrosshairRepo />} />
                  <Route path="/donate/:username" element={<DonatePage />} />
                  <Route
                    path="/:username/game-queue/overlay"
                    element={
                      <Suspense fallback={null}>
                        <GameQueueOverlay />
                      </Suspense>
                    }
                  />
                  <Route
                    path="/:username/video-queue/overlay"
                    element={
                      <Suspense fallback={null}>
                        <VideoQueueOverlay />
                      </Suspense>
                    }
                  />
                  {import.meta.env.DEV && TypographyDemo && (
                    <Route path="/dev/typography" element={<TypographyDemo />} />
                  )}
                  <Route element={<PublicOnlyRoute />}>
                    <Route path="/login" element={<LoginPage />} />
                  </Route>
                  <Route path="/activate" element={<ActivatePage />} />
                  <Route element={<ProtectedRoute />}>
                    <Route element={<SidebarLayout />}>
                      {/* Twitch Bot Routes */}
                      <Route path="/dashboard" element={<Overview />} />
                      <Route path="/commands" element={<Commands />} />
                      <Route path="/events" element={<Events />} />
                      <Route path="/analytics/insights" element={<Insights />} />
                      <Route path="/settings" element={<Settings />} />
                      {/* Module Routes */}
                      <Route path="/timers" element={<Timers />} />
                      <Route path="/modules/chat-overlay" element={<ChatOverlayModule />} />
                      <Route path="/modules/game-queue" element={<GameQueue />} />
                      <Route path="/modules/video-queue" element={<VideoQueue />} />
                      <Route path="/modules/crosshairs" element={<CrosshairModule />} />
                      {/* Discord Bot Routes */}
                      <Route path="/docs/get-started" element={<GetStarted />} />
                      <Route path="/discord/dashboard" element={<DiscordDashboard />} />
                      {/* Owner-only Routes */}
                      <Route element={<OwnerRoute />}>
                        <Route path="/admin" element={<AdminPage />} />
                        <Route path="/admin/status" element={<AdminSystemStatus />} />
                        <Route path="/admin/codes" element={<AdminActivationCodes />} />
                      </Route>
                    </Route>
                  </Route>
                  <Route path="*" element={<NotFound />} />
                </Routes>
              </Suspense>
            </ErrorBoundary>
            <Toaster position="bottom-right" richColors />
          </BotProvider>
        </ServiceStatusProvider>
      </ThemeProvider>
    </AuthProvider>
  )
}

export default App
