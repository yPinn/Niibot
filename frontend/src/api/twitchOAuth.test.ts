import { afterEach, describe, expect, it, vi } from 'vitest'

import { getTwitchOAuthUrl, openTwitchOAuth } from './twitchOAuth'

describe('getTwitchOAuthUrl', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns a trusted Twitch authorization URL', async () => {
    const oauthUrl = 'https://id.twitch.tv/oauth2/authorize?client_id=test'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ oauth_url: oauthUrl })))

    await expect(getTwitchOAuthUrl()).resolves.toBe(oauthUrl)
  })

  it('turns an HTML SPA fallback into a user-safe API error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response('<!doctype html><html></html>', {
          status: 200,
          headers: { 'Content-Type': 'text/html' },
        })
      )
    )

    await expect(getTwitchOAuthUrl()).rejects.toMatchObject({
      code: 'PARSE',
      message: '登入服務暫時無法使用，請稍後再試',
    })
  })

  it('does not emit a session-expired redirect event from the public login endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json(
            { detail: 'Login unavailable' },
            { status: 401, statusText: 'Unauthorized' }
          )
        )
    )
    const listener = vi.fn()
    window.addEventListener('auth:unauthorized', listener)

    await expect(getTwitchOAuthUrl()).rejects.toMatchObject({ status: 401 })

    window.removeEventListener('auth:unauthorized', listener)
    expect(listener).not.toHaveBeenCalled()
  })

  it('coalesces concurrent OAuth starts into one request', async () => {
    const oauthUrl = 'https://id.twitch.tv/oauth2/authorize?client_id=test'
    const fetchMock = vi.fn().mockResolvedValue(Response.json({ oauth_url: oauthUrl }))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('location', { href: 'http://localhost/settings' })

    await Promise.all([openTwitchOAuth(), openTwitchOAuth(), openTwitchOAuth()])

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(window.location.href).toBe(oauthUrl)
  })
})
