import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import type { User } from '@/api/user'
import { ProtectedRoute, PublicOnlyRoute } from '@/components/ProtectedRoute'
import { useAuth } from '@/contexts/AuthContext'

vi.mock('@/contexts/AuthContext')
vi.mock('@/components/LoadingSpinner', () => ({
  LoadingSpinner: () => <div data-testid="loading-spinner">Loading...</div>,
}))

const mockUseAuth = useAuth as MockedFunction<typeof useAuth>

const TWITCH_USER: User = {
  id: 'u1',
  name: 'streamer',
  display_name: 'Streamer',
  avatar: '',
  platform: 'twitch',
  theme: 'dark',
}

const DISCORD_USER: User = { ...TWITCH_USER, platform: 'discord' }

function makeAuthValue(overrides: Partial<ReturnType<typeof useAuth>>): ReturnType<typeof useAuth> {
  return {
    user: null,
    isAuthenticated: false,
    isInitialized: true,
    isInitError: false,
    isAffiliate: false,
    channels: [],
    logout: vi.fn(),
    refreshUser: vi.fn(),
    refreshChannels: vi.fn(),
    retryInit: vi.fn(),
    ...overrides,
  }
}

function renderProtected(
  authOverrides: Partial<ReturnType<typeof useAuth>>,
  startAt = '/dashboard'
) {
  mockUseAuth.mockReturnValue(makeAuthValue(authOverrides))
  return render(
    <MemoryRouter initialEntries={[startAt]}>
      <Routes>
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<div>Protected Content</div>} />
        </Route>
        <Route path="/login" element={<div>Login Page</div>} />
      </Routes>
    </MemoryRouter>
  )
}

function renderPublicOnly(
  authOverrides: Partial<ReturnType<typeof useAuth>>,
  startAt: string | { pathname: string; state?: unknown } = '/login'
) {
  mockUseAuth.mockReturnValue(makeAuthValue(authOverrides))
  return render(
    <MemoryRouter initialEntries={[startAt]}>
      <Routes>
        <Route element={<PublicOnlyRoute />}>
          <Route path="/login" element={<div>Login Page</div>} />
        </Route>
        <Route path="/dashboard" element={<div>Dashboard</div>} />
        <Route path="/discord/dashboard" element={<div>Discord Dashboard</div>} />
      </Routes>
    </MemoryRouter>
  )
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading spinner when not yet initialized', () => {
    renderProtected({ isInitialized: false })
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('redirects unauthenticated users to /login', () => {
    renderProtected({ isInitialized: true, isAuthenticated: false })
    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('renders child content for authenticated users', () => {
    renderProtected({ isInitialized: true, isAuthenticated: true, user: TWITCH_USER })
    expect(screen.getByText('Protected Content')).toBeInTheDocument()
  })

  it('shows error UI when isInitError is true', () => {
    renderProtected({ isInitialized: true, isInitError: true })
    expect(screen.getByText(/無法連線/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /重試/ })).toBeInTheDocument()
    expect(screen.queryByText('Protected Content')).not.toBeInTheDocument()
  })

  it('calls retryInit when retry button is clicked', async () => {
    const retryInit = vi.fn()
    renderProtected({ isInitialized: true, isInitError: true, retryInit })
    screen.getByRole('button', { name: /重試/ }).click()
    expect(retryInit).toHaveBeenCalledTimes(1)
  })
})

describe('PublicOnlyRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows login page for unauthenticated users', () => {
    renderPublicOnly({ isInitialized: true, isAuthenticated: false })
    expect(screen.getByText('Login Page')).toBeInTheDocument()
  })

  it('redirects authenticated Twitch user to /dashboard', () => {
    renderPublicOnly({ isInitialized: true, isAuthenticated: true, user: TWITCH_USER })
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.queryByText('Login Page')).not.toBeInTheDocument()
  })

  it('redirects authenticated Discord user to /discord/dashboard', () => {
    renderPublicOnly({ isInitialized: true, isAuthenticated: true, user: DISCORD_USER })
    expect(screen.getByText('Discord Dashboard')).toBeInTheDocument()
  })

  it('prevents open redirect: //evil.com is redirected to default dashboard', () => {
    renderPublicOnly(
      { isInitialized: true, isAuthenticated: true, user: TWITCH_USER },
      { pathname: '/login', state: { from: { pathname: '//evil.com' } } }
    )
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('follows a safe relative from-pathname redirect', () => {
    renderPublicOnly(
      { isInitialized: true, isAuthenticated: true, user: TWITCH_USER },
      { pathname: '/login', state: { from: { pathname: '/dashboard' } } }
    )
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
  })

  it('shows loading spinner when not yet initialized', () => {
    renderPublicOnly({ isInitialized: false })
    expect(screen.getByTestId('loading-spinner')).toBeInTheDocument()
  })
})
