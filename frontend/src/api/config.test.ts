import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { apiFetch, assertTrustedOAuthUrl } from '@/api/config'

describe('assertTrustedOAuthUrl', () => {
  it('returns the URL string for a valid Twitch OAuth URL', () => {
    const url = 'https://id.twitch.tv/oauth2/authorize?client_id=abc'
    expect(assertTrustedOAuthUrl(url, 'twitch')).toBe(url)
  })

  it('throws for null input', () => {
    expect(() => assertTrustedOAuthUrl(null, 'twitch')).toThrow('No OAuth URL returned')
  })

  it('throws for undefined input', () => {
    expect(() => assertTrustedOAuthUrl(undefined, 'twitch')).toThrow('No OAuth URL returned')
  })

  it('throws for empty string', () => {
    expect(() => assertTrustedOAuthUrl('', 'twitch')).toThrow('No OAuth URL returned')
  })

  it('throws for non-string input', () => {
    expect(() => assertTrustedOAuthUrl(42, 'twitch')).toThrow('No OAuth URL returned')
  })

  it('throws for malformed URL', () => {
    expect(() => assertTrustedOAuthUrl('not-a-url', 'twitch')).toThrow('Malformed OAuth URL')
  })

  it('throws for HTTP (non-HTTPS) URL', () => {
    expect(() => assertTrustedOAuthUrl('http://id.twitch.tv/oauth2/authorize', 'twitch')).toThrow(
      'OAuth redirect was blocked: untrusted origin'
    )
  })

  it('throws for URL with untrusted origin', () => {
    expect(() => assertTrustedOAuthUrl('https://evil.com/steal-tokens', 'twitch')).toThrow(
      'OAuth redirect was blocked: untrusted origin'
    )
  })

  it('throws when Discord URL is validated against Twitch provider', () => {
    expect(() =>
      assertTrustedOAuthUrl('https://discord.com/api/oauth2/authorize', 'twitch')
    ).toThrow('OAuth redirect was blocked: untrusted origin')
  })
})

describe('apiFetch', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('returns response on a successful request', async () => {
    const mockResponse = new Response('{}', { status: 200 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse))
    const res = await apiFetch('/api/test')
    expect(res.status).toBe(200)
    expect(fetch).toHaveBeenCalledTimes(1)
  })

  it('retries once on 503 and returns the second response', async () => {
    const fail = new Response('', { status: 503 })
    const ok = new Response('{}', { status: 200 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValueOnce(fail).mockResolvedValueOnce(ok))
    const promise = apiFetch('/api/test')
    // advance past the 1500 ms retry delay
    await vi.runAllTimersAsync()
    const res = await promise
    expect(res.status).toBe(200)
    expect(fetch).toHaveBeenCalledTimes(2)
  })

  it('dispatches auth:unauthorized event on 401 response', async () => {
    const mockResponse = new Response('', { status: 401 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse))
    const listener = vi.fn()
    window.addEventListener('auth:unauthorized', listener)
    await apiFetch('/api/test')
    window.removeEventListener('auth:unauthorized', listener)
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it('does not dispatch auth event for non-401 responses', async () => {
    const mockResponse = new Response('', { status: 200 })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(mockResponse))
    const listener = vi.fn()
    window.addEventListener('auth:unauthorized', listener)
    await apiFetch('/api/test')
    window.removeEventListener('auth:unauthorized', listener)
    expect(listener).not.toHaveBeenCalled()
  })
})
