import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

// Mock apiFetch so we never hit the network.
vi.mock('@/api/config', () => ({
  API_ENDPOINTS: {
    auth: {
      user: '/api/auth/user',
      logout: '/api/auth/logout',
      activate: '/api/auth/activate',
      pendingCode: '/api/auth/pending-code',
      requestActivation: '/api/auth/request-activation',
      activationRequest: '/api/auth/activation-request',
    },
    user: { preferences: '/api/user/preferences' },
  },
  apiFetch: vi.fn(),
}))

// Imported AFTER vi.mock so they receive the mocked version.
import { apiFetch } from '@/api/config'
import {
  activateAccount,
  getActivationRequestStatus,
  getCurrentUser,
  getPendingActivationCode,
  logout,
  requestActivation,
  updateUserPreferences,
} from '@/api/user'

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>

const MOCK_USER = {
  id: 'u1',
  name: 'streamer',
  display_name: 'Streamer',
  avatar: '',
  platform: 'twitch' as const,
  theme: 'dark' as const,
  broadcaster_type: '',
}

// ---------------------------------------------------------------------------
// getCurrentUser
// ---------------------------------------------------------------------------

describe('getCurrentUser', () => {
  beforeEach(() => {
    apiCache.clear()
    vi.clearAllMocks()
  })

  afterEach(() => {
    apiCache.clear()
  })

  it('returns user data on a 200 response', async () => {
    mockApiFetch.mockResolvedValue(new Response(JSON.stringify(MOCK_USER), { status: 200 }))
    const user = await getCurrentUser()
    expect(user?.name).toBe('streamer')
    expect(user?.platform).toBe('twitch')
  })

  it('returns null when the response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 401 }))
    const user = await getCurrentUser()
    expect(user).toBeNull()
  })

  it('returns null on 404', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 404 }))
    const user = await getCurrentUser()
    expect(user).toBeNull()
  })

  it('caches the result and avoids a second fetch', async () => {
    mockApiFetch.mockResolvedValue(new Response(JSON.stringify(MOCK_USER), { status: 200 }))
    await getCurrentUser()
    await getCurrentUser()
    expect(mockApiFetch).toHaveBeenCalledTimes(1)
  })

  it('bypasses the cache when forceRefresh is true', async () => {
    // Each call needs a fresh Response — body can only be read once.
    mockApiFetch.mockImplementation(() =>
      Promise.resolve(new Response(JSON.stringify(MOCK_USER), { status: 200 }))
    )
    await getCurrentUser()
    await getCurrentUser({ forceRefresh: true })
    expect(mockApiFetch).toHaveBeenCalledTimes(2)
  })

  it('propagates a thrown network error to the caller', async () => {
    mockApiFetch.mockRejectedValue(new Error('Network error'))
    await expect(getCurrentUser()).rejects.toThrow('Network error')
  })
})

// ---------------------------------------------------------------------------
// updateUserPreferences
// ---------------------------------------------------------------------------

describe('updateUserPreferences', () => {
  beforeEach(() => {
    apiCache.clear()
    vi.clearAllMocks()
  })

  it('sends a PATCH request with the JSON body', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await updateUserPreferences({ theme: 'dark' })
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify({ theme: 'dark' }),
      })
    )
  })

  it('patches the cached user entry with the new theme', async () => {
    apiCache.set(CACHE_KEYS.CURRENT_USER, { ...MOCK_USER, theme: 'light' })
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await updateUserPreferences({ theme: 'dark' })
    expect((apiCache.get(CACHE_KEYS.CURRENT_USER) as typeof MOCK_USER)?.theme).toBe('dark')
  })

  it('preserves other user fields when patching the cache', async () => {
    apiCache.set(CACHE_KEYS.CURRENT_USER, MOCK_USER)
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await updateUserPreferences({ theme: 'light' })
    const cached = apiCache.get(CACHE_KEYS.CURRENT_USER) as typeof MOCK_USER
    expect(cached.name).toBe('streamer')
    expect(cached.theme).toBe('light')
  })

  it('throws when the response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 500 }))
    await expect(updateUserPreferences({ theme: 'dark' })).rejects.toThrow(
      'Failed to update preferences'
    )
  })
})

// ---------------------------------------------------------------------------
// logout
// ---------------------------------------------------------------------------

describe('logout', () => {
  beforeEach(() => {
    apiCache.clear()
    vi.clearAllMocks()
  })

  it('sends a POST request to the logout endpoint', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await logout()
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ method: 'POST' })
    )
  })

  it('clears the entire API cache on success', async () => {
    apiCache.set(CACHE_KEYS.CURRENT_USER, MOCK_USER)
    apiCache.set('some-other-key', 'data')
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await logout()
    expect(apiCache.get(CACHE_KEYS.CURRENT_USER)).toBeNull()
    expect(apiCache.get('some-other-key')).toBeNull()
  })

  it('throws when the response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 500 }))
    await expect(logout()).rejects.toThrow('Failed to logout')
  })

  it('does not clear the cache when the request fails', async () => {
    apiCache.set(CACHE_KEYS.CURRENT_USER, MOCK_USER)
    mockApiFetch.mockResolvedValue(new Response('', { status: 500 }))
    try {
      await logout()
    } catch {
      /* expected */
    }
    // Cache should still be intact since logout() throws before clearing
    expect(apiCache.get(CACHE_KEYS.CURRENT_USER)).toEqual(MOCK_USER)
  })
})

// ---------------------------------------------------------------------------
// activateAccount
// ---------------------------------------------------------------------------

describe('activateAccount', () => {
  beforeEach(() => {
    apiCache.clear()
    vi.clearAllMocks()
  })

  it('resolves without error on a 200 response', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await expect(activateAccount('CODE123')).resolves.toBeUndefined()
  })

  it('sends a POST with the activation code in the body', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await activateAccount('ABC')
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/auth/activate',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ code: 'ABC' }),
      })
    )
  })

  it('patches the cached user is_activated to true on success', async () => {
    apiCache.set(CACHE_KEYS.CURRENT_USER, { ...MOCK_USER, is_activated: false })
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await activateAccount('CODE')
    expect(
      (apiCache.get(CACHE_KEYS.CURRENT_USER) as typeof MOCK_USER & { is_activated: boolean })
        ?.is_activated
    ).toBe(true)
  })

  it('throws with the server detail message on a non-ok response with JSON body', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'invalid_code' }), { status: 400 })
    )
    await expect(activateAccount('BAD')).rejects.toThrow('invalid_code')
  })

  it('throws the default message when the error body has no detail field', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 400 }))
    await expect(activateAccount('BAD')).rejects.toThrow('activation_failed')
  })

  it('throws the default message when the error body is not valid JSON', async () => {
    mockApiFetch.mockResolvedValue(new Response('not-json', { status: 400 }))
    await expect(activateAccount('BAD')).rejects.toThrow('activation_failed')
  })
})

// ---------------------------------------------------------------------------
// requestActivation
// ---------------------------------------------------------------------------

describe('requestActivation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('resolves without error on a 200 response', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await expect(requestActivation()).resolves.toBeUndefined()
  })

  it('sends a POST with no body', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))
    await requestActivation()
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/auth/request-activation',
      expect.objectContaining({ method: 'POST' })
    )
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/auth/request-activation',
      expect.not.objectContaining({ body: expect.anything() })
    )
  })

  it('throws with the server detail on a non-ok response', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'already_requested' }), { status: 409 })
    )
    await expect(requestActivation()).rejects.toThrow('already_requested')
  })

  it('throws the default message when the error body has no detail field', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 500 }))
    await expect(requestActivation()).rejects.toThrow('request_failed')
  })

  it('throws the default message when the error body is not valid JSON', async () => {
    mockApiFetch.mockResolvedValue(new Response('not-json', { status: 500 }))
    await expect(requestActivation()).rejects.toThrow('request_failed')
  })
})

// ---------------------------------------------------------------------------
// getPendingActivationCode
// ---------------------------------------------------------------------------

describe('getPendingActivationCode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns the code string on a 200 response', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ code: 'ABC123' }), { status: 200 })
    )
    const result = await getPendingActivationCode()
    expect(result).toBe('ABC123')
  })

  it('returns null when code is null in the response body', async () => {
    mockApiFetch.mockResolvedValue(new Response(JSON.stringify({ code: null }), { status: 200 }))
    const result = await getPendingActivationCode()
    expect(result).toBeNull()
  })

  it('returns null when the response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 404 }))
    const result = await getPendingActivationCode()
    expect(result).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// getActivationRequestStatus
// ---------------------------------------------------------------------------

describe('getActivationRequestStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns the status from a 200 response', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ status: 'pending', created_at: '2026-01-01' }), { status: 200 })
    )
    const result = await getActivationRequestStatus()
    expect(result).toEqual({ status: 'pending', created_at: '2026-01-01' })
  })

  it('returns { status: null } when the response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 404 }))
    const result = await getActivationRequestStatus()
    expect(result).toEqual({ status: null })
  })
})
