import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ErrorBoundary'
import SidebarLayout from '@/components/layouts/SidebarLayout'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { ThemeProvider } from '@/components/theme-provider'
import { Toaster } from '@/components/ui'
import { AuthProvider } from '@/contexts/AuthContext'
import { BotProvider } from '@/contexts/BotContext'
import { ServiceStatusProvider } from '@/contexts/ServiceStatusContext'
// Eagerly loaded: critical path or tiny bundles
import Landing from '@/pages/Landing'
import NotFound from '@/pages/NotFound'

// Lazy-loaded: large dashboard pages and overlays
const Commands = lazy(() => import('@/pages/dashboard/commands'))
const Events = lazy(() => import('@/pages/dashboard/Events'))
const Overview = lazy(() => import('@/pages/dashboard/Overview'))
const SystemStatus = lazy(() => import('@/pages/dashboard/SystemStatus'))
const DiscordDashboard = lazy(() => import('@/pages/discord/Dashboard'))
const GameQueueOverlay = lazy(() => import('@/pages/GameQueueOverlay'))
const LoginPage = lazy(() => import('@/pages/Login'))
const GameQueue = lazy(() => import('@/pages/modules/GameQueue'))
const Timers = lazy(() => import('@/pages/modules/Timers'))
const VideoQueue = lazy(() => import('@/pages/modules/VideoQueue'))
const PublicCommands = lazy(() => import('@/pages/PublicCommands'))
const GetStarted = lazy(() => import('@/pages/docs/GetStarted'))
const Terms = lazy(() => import('@/pages/docs/Terms'))
const Privacy = lazy(() => import('@/pages/docs/Privacy'))
const Settings = lazy(() => import('@/pages/Settings'))
const VideoQueueOverlay = lazy(() => import('@/pages/VideoQueueOverlay'))

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
                      <Route path="/modules/video-queue" element={<VideoQueue />} />
                      {/* Discord Bot Routes */}
                      <Route path="/docs" element={<GetStarted />} />
                      <Route path="/discord/dashboard" element={<DiscordDashboard />} />
                      <Route path="*" element={<NotFound />} />
                    </Route>
                  </Route>
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
