import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  getCommunityOverlayFeed,
  getCommunityOverlaySettings,
  getCommunityOverlayTheme,
  getCommunityOverlayThemeSettings,
  publishCommunityOverlayTheme,
  resetCommunityOverlayThemeDraft,
  rotateCommunityOverlayKey,
  updateCommunityOverlaySettings,
  updateCommunityOverlayThemeDraft,
} from './communityOverlay'

describe('getCommunityOverlayFeed', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('keeps the capability out of the URL and sends it in a header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ cursor: 13, events: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCommunityOverlayFeed('11111111-1111-4111-8111-111111111111', 12)

    expect(fetchMock).toHaveBeenCalledOnce()
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'https://niibot.tv')
    expect(url.pathname).toBe('/api/community-overlay/public/events')
    expect(url.searchParams.has('key')).toBe(false)
    expect(url.searchParams.get('after_id')).toBe('12')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      headers: { 'X-Overlay-Key': '11111111-1111-4111-8111-111111111111' },
    })
  })

  it('omits after_id for the no-replay handshake', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ cursor: 13, events: [] }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCommunityOverlayFeed('key-only')

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'https://niibot.tv')
    expect(url.searchParams.has('after_id')).toBe(false)
    expect(url.searchParams.has('key')).toBe(false)
  })
})

describe('community overlay settings', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads the authenticated tenant settings', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ public_key: 'key', enabled: true }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCommunityOverlaySettings()

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/community-overlay/settings'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('updates the enabled state with JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ public_key: 'key', enabled: false }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await updateCommunityOverlaySettings(false)

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/community-overlay/settings'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: false }),
    })
  })

  it('rotates the tenant capability key', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ public_key: 'new-key', enabled: true }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await rotateCommunityOverlayKey()

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/community-overlay/settings/rotate-key'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'community-overlay' },
    })
  })
})

describe('community overlay tenant theme', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads the published theme using the capability key', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: vi.fn().mockResolvedValue({ theme: DEFAULT_COMMUNITY_OVERLAY_THEME }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCommunityOverlayTheme('key with spaces')

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'https://niibot.tv')
    expect(url.pathname).toBe('/api/community-overlay/public/theme')
    expect(url.searchParams.has('key')).toBe(false)
    expect(fetchMock.mock.calls[0][1]).toEqual({
      headers: { 'X-Overlay-Key': 'key with spaces' },
    })
  })

  it('loads the authenticated tenant draft and published state', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ draft: DEFAULT_COMMUNITY_OVERLAY_THEME }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCommunityOverlayThemeSettings()

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/community-overlay/settings/theme'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('saves a complete draft as JSON', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ draft: DEFAULT_COMMUNITY_OVERLAY_THEME }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await updateCommunityOverlayThemeDraft(DEFAULT_COMMUNITY_OVERLAY_THEME, 3)

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/community-overlay/settings/theme/draft'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
        expected_draft_version: 3,
      }),
    })
  })

  it.each([
    [publishCommunityOverlayTheme, '/api/community-overlay/settings/theme/publish'],
    [resetCommunityOverlayThemeDraft, '/api/community-overlay/settings/theme/reset-draft'],
  ] as const)('posts a theme lifecycle action', async (action, path) => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ draft: DEFAULT_COMMUNITY_OVERLAY_THEME }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await action(3)

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(path)
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-Niibot-Action': 'community-overlay',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ expected_draft_version: 3 }),
    })
  })
})
