import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/config', () => ({
  API_ENDPOINTS: {
    channels: {
      twitch: {
        monitored: '/api/channels/twitch/monitored',
        myStatus: '/api/channels/twitch/my-status',
        toggle: '/api/channels/twitch/toggle',
        modStatus: '/api/channels/twitch/mod-status',
        grantMod: '/api/channels/twitch/grant-mod',
      },
      defaults: '/api/channels/defaults',
    },
  },
  apiFetch: vi.fn(),
}))

vi.mock('@/lib/apiCache', () => ({
  apiCache: { clear: vi.fn(), fetch: vi.fn(), get: vi.fn(), set: vi.fn(), invalidate: vi.fn() },
  CACHE_KEYS: { CHANNELS: 'channels:twitch-monitored' },
}))

import { getBotModStatus, grantBotMod } from '@/api/channels'
import { apiFetch } from '@/api/config'

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>

beforeEach(() => vi.clearAllMocks())
afterEach(() => vi.restoreAllMocks())

// ---------------------------------------------------------------------------
// getBotModStatus
// ---------------------------------------------------------------------------

describe('getBotModStatus', () => {
  it('returns ok result with data when response is ok', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ is_moderator: true }), { status: 200 })
    )
    const result = await getBotModStatus()
    expect(result).toEqual({ ok: true, data: { is_moderator: true } })
  })

  it('returns error result with status when response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 403 }))
    const result = await getBotModStatus()
    expect(result).toEqual({ ok: false, status: 403 })
  })

  it('returns error result with status 0 when apiFetch throws', async () => {
    mockApiFetch.mockRejectedValue(new Error('network error'))
    const result = await getBotModStatus()
    expect(result).toEqual({ ok: false, status: 0 })
  })

  it('calls the correct endpoint with credentials', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ is_moderator: false }), { status: 200 })
    )
    await getBotModStatus()
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/channels/twitch/mod-status',
      expect.objectContaining({ credentials: 'include' })
    )
  })
})

// ---------------------------------------------------------------------------
// grantBotMod
// ---------------------------------------------------------------------------

describe('grantBotMod', () => {
  it('returns GrantModResponse when granted', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ granted: true, already_mod: false }), { status: 200 })
    )
    const result = await grantBotMod()
    expect(result).toEqual({ granted: true, already_mod: false })
  })

  it('returns GrantModResponse when already_mod', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ granted: false, already_mod: true }), { status: 200 })
    )
    const result = await grantBotMod()
    expect(result).toEqual({ granted: false, already_mod: true })
  })

  it('throws when response is not ok', async () => {
    mockApiFetch.mockResolvedValue(new Response('', { status: 500 }))
    await expect(grantBotMod()).rejects.toThrow('Failed to grant moderator status')
  })

  it('calls the correct endpoint with POST and credentials', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ granted: true, already_mod: false }), { status: 200 })
    )
    await grantBotMod()
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/channels/twitch/grant-mod',
      expect.objectContaining({ method: 'POST', credentials: 'include' })
    )
  })
})
