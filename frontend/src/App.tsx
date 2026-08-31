import { lazy, Suspense } from 'react'
import { Route, Routes } from 'react-router-dom'

import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ThemeProvider } from '@/components/layout/theme-provider'
import { LoadingSpinner } from '@/components/LoadingSpinner'
import { OwnerRoute, ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { Toaster } from '@/components/ui'
import { AuthProvider } from '@/contexts/AuthContext'
import { BotProvider } from '@/contexts/BotContext'
import { ServiceStatusProvider } from '@/contexts/ServiceStatusContext'
import { TenantProvider } from '@/contexts/TenantContext'
// Lazy-loaded: all pages including Landing and NotFound to keep motion out of main bundle.
// SidebarLayout is lazy too — it pulls the full radix sidebar/nav tree that public
// routes (landing, login, overlays) never render.
const SidebarLayout = lazy(() => import('@/components/layout/SidebarLayout'))
const Landing = lazy(() => import('@/pages/Landing'))
const NotFound = lazy(() => import('@/pages/NotFound'))
const Commands = lazy(() => import('@/pages/dashboard/commands'))
const Events = lazy(() => import('@/pages/dashboard/events'))
const ChannelPoints = lazy(() => import('@/pages/dashboard/channelPoints'))
const Overview = lazy(() => import('@/pages/dashboard/Overview'))
const Timers = lazy(() => import('@/pages/dashboard/Timers'))
const AdminPage = lazy(() => import('@/pages/admin'))
const AdminMonitor = lazy(() => import('@/pages/admin/Monitor'))
const AdminModules = lazy(() => import('@/pages/admin/Modules'))
const Insights = lazy(() => import('@/pages/analytics/Insights'))
const Matcher = lazy(() => import('@/pages/analytics/Matcher'))
const DiscordDashboard = lazy(() => import('@/pages/discord/Dashboard'))
const GameQueueOverlay = lazy(() => import('@/pages/GameQueueOverlay'))
const LoginPage = lazy(() => import('@/pages/Login'))
const GameQueue = lazy(() => import('@/pages/modules/GameQueue'))
const VideoQueue = lazy(() => import('@/pages/modules/VideoQueue'))
const CrosshairModule = lazy(() => import('@/pages/modules/crosshairs'))
const AIModule = lazy(() => import('@/pages/modules/AI'))
const CrosshairRepo = lazy(() => import('@/pages/crosshairs'))
const PublicCommands = lazy(() => import('@/pages/PublicCommands'))
const DonatePage = lazy(() => import('@/pages/DonatePage'))
const GetStarted = lazy(() => import('@/pages/docs/GetStarted'))
const Releases = lazy(() => import('@/pages/docs/Releases'))
const Terms = lazy(() => import('@/pages/Terms'))
const Privacy = lazy(() => import('@/pages/Privacy'))
const Settings = lazy(() => import('@/pages/Settings'))
const VideoQueueOverlay = lazy(() => import('@/pages/VideoQueueOverlay'))
const CommunityOverlay = lazy(() => import('@/pages/CommunityOverlay'))
const CommunityOverlaySettings = lazy(() => import('@/pages/modules/CommunityOverlaySettings'))
const ActivatePage = lazy(() => import('@/pages/activate'))
const SupportPage = lazy(() => import('@/pages/Support'))
const BotInvite = lazy(() => import('@/pages/BotInvite'))
const BotAuthorizationResult = lazy(() => import('@/pages/BotAuthorizationResult'))

// Dev-only: excluded from production bundle via dead-code elimination
const TypographyDemo = import.meta.env.DEV ? lazy(() => import('@/pages/TypographyDemo')) : null

function App() {
  return (
    <AuthProvider>
      <TenantProvider>
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
                    <Route path="/bot-invite/:publicToken" element={<BotInvite />} />
                    <Route path="/bot-auth/result" element={<BotAuthorizationResult />} />
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
                    <Route
                      path="/live-display"
                      element={
                        <Suspense fallback={null}>
                          <CommunityOverlay />
                        </Suspense>
                      }
                    />
                    {import.meta.env.DEV && TypographyDemo && (
                      <Route path="/dev/typography" element={<TypographyDemo />} />
                    )}
                    {import.meta.env.DEV && (
                      <Route path="/dev/activate" element={<ActivatePage preview />} />
                    )}
                    {import.meta.env.DEV && (
                      <Route
                        path="/dev/live-display"
                        element={<CommunityOverlaySettings preview />}
                      />
                    )}
                    <Route element={<PublicOnlyRoute />}>
                      <Route path="/login" element={<LoginPage />} />
                    </Route>
                    <Route path="/activate" element={<ActivatePage />} />
                    <Route element={<ProtectedRoute />}>
                      <Route element={<SidebarLayout />}>
                        {/* Twitch Bot Routes */}
                        <Route path="/dashboard" element={<Overview />} />
                        <Route path="/dashboard/:channelId" element={<Overview />} />
                        <Route path="/commands" element={<Commands />} />
                        <Route path="/events" element={<Events />} />
                        <Route path="/channel-points" element={<ChannelPoints />} />
                        <Route path="/analytics/insights" element={<Insights />} />
                        <Route path="/analytics/matcher" element={<Matcher />} />
                        <Route path="/settings" element={<Settings />} />
                        {/* Module Routes */}
                        <Route path="/timers" element={<Timers />} />
                        <Route path="/modules/game-queue" element={<GameQueue />} />
                        <Route path="/modules/video-queue" element={<VideoQueue />} />
                        <Route
                          path="/modules/live-display"
                          element={<CommunityOverlaySettings />}
                        />
                        <Route path="/modules/crosshairs" element={<CrosshairModule />} />
                        <Route path="/modules/ai" element={<AIModule />} />
                        <Route path="/support" element={<SupportPage />} />
                        {/* Discord Bot Routes */}
                        <Route path="/docs/get-started" element={<GetStarted />} />
                        <Route path="/docs/releases" element={<Releases />} />
                        <Route path="/discord" element={<DiscordDashboard />} />
                        {/* Owner-only Routes */}
                        <Route element={<OwnerRoute />}>
                          <Route path="/admin" element={<AdminPage />} />
                          <Route path="/admin/monitor" element={<AdminMonitor />} />
                          <Route path="/admin/modules" element={<AdminModules />} />
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
      </TenantProvider>
    </AuthProvider>
  )
}

export default App
