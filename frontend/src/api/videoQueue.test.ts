import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import {
  advanceVideoQueue,
  advanceVideoQueueFromDashboard,
  getVideoQueueRankings,
  reportPlaybackStarted,
  reportVideoMetadata,
  rotateVideoQueueOverlayKey,
} from './videoQueue'

const OVERLAY_KEY = '11111111-1111-4111-8111-111111111111'

function okResponse(body: object = {}) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: vi.fn().mockResolvedValue(body),
  }
}

describe('video queue overlay capability', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the capability out of the URL and sends it on advance', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal('fetch', fetchMock)

    await advanceVideoQueue('streamer', 5, OVERLAY_KEY, 'provider_error')

    const url = requestUrl(fetchMock.mock.calls[0][0])
    expect(url.pathname).toBe('/api/video-queue/public/streamer/advance')
    expect(url.searchParams.has('key')).toBe(false)
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Overlay-Key': OVERLAY_KEY },
      body: JSON.stringify({ done_id: 5, reason: 'provider_error' }),
    })
  })

  it('sends the capability when reporting fallback metadata', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal('fetch', fetchMock)

    await reportVideoMetadata('streamer', 7, 120, OVERLAY_KEY)

    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', 'X-Overlay-Key': OVERLAY_KEY },
      body: JSON.stringify({ duration_seconds: 120 }),
    })
  })

  it('reports an idempotent playback-start signal with the capability', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal('fetch', fetchMock)

    await reportPlaybackStarted('streamer', 7, 'best_effort', OVERLAY_KEY)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(
      '/api/video-queue/public/streamer/entries/7/playback-started'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Overlay-Key': OVERLAY_KEY },
      body: JSON.stringify({ signal: 'best_effort' }),
    })
  })

  it('uses the authenticated endpoint for dashboard kickstart', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse())
    vi.stubGlobal('fetch', fetchMock)

    await advanceVideoQueueFromDashboard(null)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/video-queue/advance')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ done_id: null }),
    })
  })

  it('rotates the capability through an authenticated action endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse({ overlay_key: 'new-key' }))
    vi.stubGlobal('fetch', fetchMock)

    await rotateVideoQueueOverlayKey()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe(
      '/api/video-queue/settings/rotate-key'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'video-queue' },
    })
  })

  it('loads a private ranking with closed filters', async () => {
    const fetchMock = vi.fn().mockResolvedValue(okResponse([]))
    vi.stubGlobal('fetch', fetchMock)

    await getVideoQueueRankings('global', 30, 'youtube')

    const url = requestUrl(fetchMock.mock.calls[0][0])
    expect(url.pathname).toBe('/api/video-queue/rankings')
    expect(url.searchParams.toString()).toBe('scope=global&days=30&video_type=youtube')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })
})
