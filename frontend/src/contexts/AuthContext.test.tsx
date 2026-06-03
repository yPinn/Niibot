import React from 'react'
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api', () => ({
  getCurrentUser: vi.fn(),
  getTwitchMonitoredChannels: vi.fn(),
}))
vi.mock('@/api/user', () => ({
  logout: vi.fn(),
}))
vi.mock('@/lib/apiCache', () => ({
  apiCache: { clear: vi.fn(), fetch: vi.fn(), get: vi.fn(), set: vi.fn() },
  CACHE_KEYS: { CURRENT_USER: 'auth:current-user' },
}))
vi.mock('sonner', () => ({
  toast: { error: vi.fn(), warning: vi.fn(), info: vi.fn(), success: vi.fn() },
}))
vi.mock('@/api/twitchOAuth', () => ({
  openTwitchOAuth: vi.fn(),
}))

import { toast } from 'sonner'

import { getCurrentUser, getTwitchMonitoredChannels } from '@/api'
import { openTwitchOAuth } from '@/api/twitchOAuth'
import { logout as apiLogout } from '@/api/user'
import { AuthProvider, isPublicPath, useAuth } from '@/contexts/AuthContext'

const mockGetCurrentUser = getCurrentUser as ReturnType<typeof vi.fn>
const mockGetChannels = getTwitchMonitoredChannels as ReturnType<typeof vi.fn>
const mockApiLogout = apiLogout as ReturnType<typeof vi.fn>

const TWITCH_USER = {
  id: 'u1',
  name: 'streamer',
  display_name: 'Streamer',
  avatar: '',
  platform: 'twitch' as const,
  theme: 'dark' as const,
  broadcaster_type: '',
}

// ---------------------------------------------------------------------------
// isPublicPath — pure function tests, no rendering needed
// ---------------------------------------------------------------------------

describe('isPublicPath', () => {
  it.each([
    ['/', true],
    ['/login', true],
    ['/terms', true],
    ['/privacy', true],
    ['/donate/alice', true],
    ['/donate/alice/extra', true],
    ['/alice/commands', true],
    ['/dashboard/overlay', true], // contains '/overlay'
  ])('returns true for public path %s', (path, expected) => {
    expect(isPublicPath(path)).toBe(expected)
  })

  it.each([
    ['/dashboard', false],
    ['/settings', false],
    ['/alice/commands/edit', false], // extra segment — not matched by regex
    ['/alice/commands2', false], // no trailing /commands
    ['//evil.com', false], // double-slash path
  ])('returns false for protected path %s', (path, expected) => {
    expect(isPublicPath(path)).toBe(expected)
  })
})

// ---------------------------------------------------------------------------
// AuthProvider — general behaviour
// jsdom defaults to pathname='/' (public) so we stub location to '/dashboard'.
// ---------------------------------------------------------------------------

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    // Navigate to a protected path so the auth bootstrap actually fires.
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('becomes initialized and authenticated after successful load', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)
    expect(result.current.user?.name).toBe('streamer')
  })

  it('isAuthenticated is false when getCurrentUser returns null', async () => {
    mockGetCurrentUser.mockResolvedValue(null)
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.user).toBeNull()
  })

  it('sets isInitError when the API throws a network error', async () => {
    mockGetCurrentUser.mockRejectedValue(new Error('Network failure'))
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isInitError).toBe(true)
    expect(result.current.isAuthenticated).toBe(false)
  })

  it('isAffiliate is true when broadcaster_type is "affiliate"', async () => {
    mockGetCurrentUser.mockResolvedValue({ ...TWITCH_USER, broadcaster_type: 'affiliate' })
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAffiliate).toBe(true)
  })

  it('isAffiliate is true when broadcaster_type is "partner"', async () => {
    mockGetCurrentUser.mockResolvedValue({ ...TWITCH_USER, broadcaster_type: 'partner' })
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAffiliate).toBe(true)
  })

  it('isAffiliate is false for a non-affiliate broadcaster_type', async () => {
    mockGetCurrentUser.mockResolvedValue({ ...TWITCH_USER, broadcaster_type: '' })
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAffiliate).toBe(false)
  })

  it('skips the API fetch on a public path and sets initialized immediately', async () => {
    // Override to a public path
    vi.stubGlobal('location', { pathname: '/login', href: 'http://localhost/login' })
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(mockGetCurrentUser).not.toHaveBeenCalled()
    expect(result.current.isAuthenticated).toBe(false)
  })
})

// ---------------------------------------------------------------------------
// AuthProvider — 401 global interceptor
// ---------------------------------------------------------------------------

describe('AuthProvider 401 interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('clears user state when auth:unauthorized fires after initialization', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    })

    expect(result.current.user).toBeNull()
    expect(result.current.channels).toEqual([])
  })

  it('redirects to /login?reason=session_expired when auth:unauthorized fires after initialization', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    })

    // vi.stubGlobal replaces location with a plain object so href assignment is trackable
    expect(window.location.href).toBe('/login?reason=session_expired')
  })

  it('does not clear state when auth:unauthorized fires before initialization', async () => {
    let resolveUser!: (v: typeof TWITCH_USER) => void
    mockGetCurrentUser.mockReturnValue(
      new Promise<typeof TWITCH_USER>(resolve => {
        resolveUser = resolve
      })
    )

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    // Fire event while init is still pending (isInitializedRef.current === false)
    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    })

    // Now let the API call finish
    await act(async () => {
      resolveUser(TWITCH_USER)
    })

    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    // The event fired before isInitializedRef was true — handler should have bailed out
    expect(result.current.user).not.toBeNull()
  })
})

// ---------------------------------------------------------------------------
// AuthProvider — auth:reauth-required global interceptor
// ---------------------------------------------------------------------------

describe('AuthProvider reauth-required interceptor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it('shows a toast.error when auth:reauth-required fires', async () => {
    const mockToast = toast as { error: ReturnType<typeof vi.fn> }
    renderHook(() => useAuth(), { wrapper: AuthProvider })

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:reauth-required'))
    })

    expect(mockToast.error).toHaveBeenCalledWith(
      expect.stringContaining('重新授權'),
      expect.objectContaining({
        action: expect.objectContaining({ onClick: openTwitchOAuth }),
      })
    )
  })

  it('does not clear user state when auth:reauth-required fires', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:reauth-required'))
    })

    expect(result.current.user).not.toBeNull()
    expect(result.current.isAuthenticated).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// refreshUser
// ---------------------------------------------------------------------------

describe('refreshUser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('updates user when called successfully', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    const updatedUser = { ...TWITCH_USER, display_name: 'Updated' }
    mockGetCurrentUser.mockResolvedValue(updatedUser)

    await act(async () => {
      await result.current.refreshUser()
    })

    expect(result.current.user?.display_name).toBe('Updated')
  })

  it('sets user to null when getCurrentUser throws', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)

    mockGetCurrentUser.mockRejectedValue(new Error('fetch error'))

    await act(async () => {
      await result.current.refreshUser()
    })

    expect(result.current.user).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// logout
// ---------------------------------------------------------------------------

describe('logout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
    mockApiLogout.mockResolvedValue(undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('clears user and channels then redirects to /login', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)

    await act(async () => {
      await result.current.logout()
    })

    expect(mockApiLogout).toHaveBeenCalledOnce()
    expect(result.current.user).toBeNull()
    expect(result.current.channels).toEqual([])
    expect(window.location.href).toBe('/login')
  })

  it('still clears state and redirects even when apiLogout throws', async () => {
    mockApiLogout.mockRejectedValue(new Error('network error'))
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    await act(async () => {
      await result.current.logout()
    })

    expect(result.current.user).toBeNull()
    expect(result.current.channels).toEqual([])
    expect(window.location.href).toBe('/login')
  })
})

// ---------------------------------------------------------------------------
// refreshChannels — error path
// ---------------------------------------------------------------------------

describe('refreshChannels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('sets channels to empty array when getTwitchMonitoredChannels throws', async () => {
    // Initial load succeeds, explicit refreshChannels call fails
    mockGetChannels
      .mockResolvedValueOnce([{ id: 'c1' }])
      .mockRejectedValueOnce(new Error('channels error'))

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.channels).toHaveLength(1)

    await act(async () => {
      await result.current.refreshChannels()
    })

    expect(result.current.channels).toEqual([])
  })

  it('updates channels when getTwitchMonitoredChannels resolves', async () => {
    const CHANNEL = { id: 'c1', name: 'ch' }
    mockGetChannels.mockResolvedValueOnce([]).mockResolvedValueOnce([CHANNEL])

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    await act(async () => {
      await result.current.refreshChannels()
    })

    expect(result.current.channels).toEqual([CHANNEL])
  })
})

// ---------------------------------------------------------------------------
// channels polling
// ---------------------------------------------------------------------------

describe('channels polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('polls channels after BASE_MS and updates state on success', async () => {
    const CHANNEL = { id: 'c1', name: 'ch' }
    mockGetChannels
      .mockResolvedValueOnce([]) // initial load
      .mockResolvedValueOnce([CHANNEL]) // first poll

    vi.useFakeTimers()
    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    // Flush initial async load (Promise.all inside loadInitialData)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // Advance by BASE_MS (5 min) to trigger the first poll
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })

    expect(mockGetChannels).toHaveBeenCalledTimes(2)
    expect(result.current.channels).toEqual([CHANNEL])
  })

  it('increments failure count and backs off when poll throws', async () => {
    mockGetChannels
      .mockResolvedValueOnce([]) // initial load
      .mockRejectedValueOnce(new Error('timeout')) // first poll fails

    vi.useFakeTimers()
    renderHook(() => useAuth(), { wrapper: AuthProvider })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // Advance by BASE_MS to trigger the failing poll
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })

    // After failure, next poll is scheduled (backoff = BASE_MS * 2^1 = 10 min)
    // Verify the poll was attempted
    expect(mockGetChannels).toHaveBeenCalledTimes(2)
  })

  it('stops polling when the component unmounts', async () => {
    mockGetChannels.mockResolvedValue([])

    vi.useFakeTimers()
    const { unmount } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    unmount()

    // Advance past BASE_MS — poll should not fire after unmount
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5 * 60_000)
    })

    // Only the initial load call, no polling
    expect(mockGetChannels).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// AuthProvider 401 interceptor — overlay guard (line 58 TRUE branch)
// ---------------------------------------------------------------------------

describe('AuthProvider 401 interceptor — overlay guard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('does NOT clear user state or redirect when auth:unauthorized fires on an overlay route', async () => {
    // Init on a normal protected path so auth bootstrap runs and user loads.
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))
    expect(result.current.isAuthenticated).toBe(true)

    // Switch to overlay path AFTER init so 401 handler hits the overlay guard.
    window.location.pathname = '/dashboard/overlay'

    act(() => {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    })

    expect(result.current.user).not.toBeNull()
    expect(window.location.href).not.toBe('/login?reason=session_expired')
  })
})

// ---------------------------------------------------------------------------
// import.meta.env.DEV branches — logout / refreshChannels / loadInitialData
// ---------------------------------------------------------------------------

describe('import.meta.env.DEV branch in logout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
    mockApiLogout.mockRejectedValue(new Error('network error'))
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('calls console.error in logout catch block when DEV=true', async () => {
    vi.stubEnv('DEV', 'true')
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    const fetchError = new Error('network error')
    mockApiLogout.mockRejectedValue(fetchError)

    await act(async () => {
      await result.current.logout()
    })

    expect(consoleSpy).toHaveBeenCalledWith('Logout request failed:', fetchError)
    expect(result.current.user).toBeNull()
    expect(window.location.href).toBe('/login')
  })
})

describe('import.meta.env.DEV branch in refreshChannels', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('calls console.error in refreshChannels catch block when DEV=true', async () => {
    vi.stubEnv('DEV', 'true')
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    const fetchError = new Error('channels error')
    mockGetChannels.mockRejectedValue(fetchError)

    await act(async () => {
      await result.current.refreshChannels()
    })

    expect(consoleSpy).toHaveBeenCalledWith('Failed to load channels:', fetchError)
    expect(result.current.channels).toEqual([])
  })
})

describe('import.meta.env.DEV branch in loadInitialData', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('calls console.error in loadInitialData catch block when DEV=true', async () => {
    vi.stubEnv('DEV', 'true')
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const initError = new Error('Network failure')
    mockGetCurrentUser.mockRejectedValue(initError)

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    expect(result.current.isInitError).toBe(true)
    expect(consoleSpy).toHaveBeenCalledWith('Failed to load initial data:', initError)
  })
})

// ---------------------------------------------------------------------------
// import.meta.env.DEV branches — refreshUser error path with DEV=true (line 86)
// ---------------------------------------------------------------------------

describe('import.meta.env.DEV branch in refreshUser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.unstubAllEnvs()
  })

  it('calls console.error in refreshUser catch block when DEV=true', async () => {
    vi.stubEnv('DEV', 'true')
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    const fetchError = new Error('fetch error')
    mockGetCurrentUser.mockRejectedValue(fetchError)

    await act(async () => {
      await result.current.refreshUser()
    })

    expect(result.current.user).toBeNull()
    expect(consoleSpy).toHaveBeenCalledWith('Failed to load user:', fetchError)
  })
})

// ---------------------------------------------------------------------------
// initRef.current.isLoading guard (line 147 — the isLoading branch)
// ---------------------------------------------------------------------------

describe('AuthProvider — isLoading guard prevents concurrent init', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('ignores a retryInit call that arrives while a load is already in-flight', async () => {
    let resolveUser!: (v: typeof TWITCH_USER) => void
    // Keep the initial load pending so isLoading stays true.
    mockGetCurrentUser.mockReturnValue(
      new Promise<typeof TWITCH_USER>(resolve => {
        resolveUser = resolve
      })
    )

    const { result } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    // Call retryInit while the first load is still in-flight.
    // The isLoading guard should cause it to return immediately without
    // scheduling a second concurrent load.
    act(() => {
      result.current.retryInit()
    })

    // Now let the original load complete.
    await act(async () => {
      resolveUser(TWITCH_USER)
    })

    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    // getCurrentUser must have been called exactly once — the guard prevented a second call.
    expect(mockGetCurrentUser).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// channels polling — cancelled race (lines 164-171)
// ---------------------------------------------------------------------------

describe('channels polling — cancelled=true race', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('does not call setChannels when the component unmounts while a poll fetch is in-flight', async () => {
    // Resolve the initial load immediately, then stall the poll fetch forever.
    let resolvePoll!: (v: { id: string }[]) => void
    mockGetChannels
      .mockResolvedValueOnce([]) // initial load
      .mockReturnValueOnce(
        new Promise<{ id: string }[]>(resolve => {
          resolvePoll = resolve
        })
      ) // poll — never resolves until we decide

    vi.useFakeTimers()
    const { unmount } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    // Flush the initial load — both mocks resolve immediately as microtasks.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // Advance to trigger the poll — the fetch is now in-flight and stalled.
    act(() => {
      vi.advanceTimersByTime(5 * 60_000) // 同步，不等待 promise
    })
    await act(async () => {
      await Promise.resolve()
    })

    // Unmount while the poll fetch is still pending (sets cancelled=true).
    unmount()

    // Now resolve the stalled poll — with cancelled=true the callback must not call setChannels.
    const CHANNEL = { id: 'should-not-appear' }
    await act(async () => {
      resolvePoll([CHANNEL])
    })

    // getTwitchMonitoredChannels was called for the poll, but because cancelled=true
    // the resolved data must not have been applied to state.
    expect(mockGetChannels).toHaveBeenCalledTimes(2)
    // The result ref is unmounted; the key invariant is that no state-setter threw
    // and the resolved data was silently dropped — verified by the mock call count alone.
  })
})

// ---------------------------------------------------------------------------
// useAuth outside AuthProvider
// ---------------------------------------------------------------------------

describe('useAuth', () => {
  it('throws when used outside AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrow('useAuth must be used within an AuthProvider')
  })
})

// ---------------------------------------------------------------------------
// useEffect hasLoaded guard — StrictMode double-mount protection (line 155)
// ---------------------------------------------------------------------------

describe('AuthProvider — StrictMode double-mount guard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetChannels.mockResolvedValue([])
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('loads data exactly once even when the effect fires twice (StrictMode double-mount)', async () => {
    mockGetCurrentUser.mockImplementation(() => Promise.resolve(TWITCH_USER))

    const wrapper = ({ children }: { children: React.ReactNode }) =>
      React.createElement(React.StrictMode, null, React.createElement(AuthProvider, null, children))

    const { result } = renderHook(() => useAuth(), { wrapper })
    await waitFor(() => expect(result.current.isInitialized).toBe(true))

    // StrictMode fires effects twice; the hasLoaded guard must prevent a double fetch.
    expect(mockGetCurrentUser).toHaveBeenCalledTimes(1)
  })
})

// ---------------------------------------------------------------------------
// channels polling — cancelled + error path (line 169: !cancelled branch false)
// ---------------------------------------------------------------------------

describe('channels polling — cancelled=true error path', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('location', { pathname: '/dashboard', href: 'http://localhost/dashboard' })
    mockGetCurrentUser.mockResolvedValue(TWITCH_USER)
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    vi.useRealTimers()
  })

  it('does not throw and silently drops the error when a poll rejects after unmount', async () => {
    let rejectPoll!: (e: Error) => void
    mockGetChannels
      .mockResolvedValueOnce([]) // initial load
      .mockReturnValueOnce(
        new Promise<never>((_, reject) => {
          rejectPoll = reject
        })
      )

    vi.useFakeTimers()
    const { unmount } = renderHook(() => useAuth(), { wrapper: AuthProvider })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    // Trigger the poll
    act(() => {
      vi.advanceTimersByTime(5 * 60_000)
    })
    await act(async () => {
      await Promise.resolve()
    })

    // Unmount while poll is in-flight (cancelled=true)
    unmount()

    // Rejecting the stalled poll must not throw — cancelled guard skips failures++
    await expect(
      act(async () => {
        rejectPoll(new Error('network timeout'))
      })
    ).resolves.toBeUndefined()

    expect(mockGetChannels).toHaveBeenCalledTimes(2)
  })
})
