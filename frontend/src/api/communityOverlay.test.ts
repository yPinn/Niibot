import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
  getCommunityOverlayFeed,
  getCommunityOverlaySettings,
  getCommunityOverlayTheme,
  getCommunityOverlayThemeSettings,
  publishCommunityOverlayTheme,
  resetCommunityOverlayThemeDraft,
  rotateCommunityOverlayKey,
  triggerCommunityOverlayPreview,
  updateCommunityOverlaySettings,
  updateCommunityOverlayThemeDraft,
} from './communityOverlay'

describe('Live Display defaults', () => {
  it('avoids the usual bottom-right camera area and gives Tarot a longer hold', () => {
    expect(DEFAULT_COMMUNITY_OVERLAY_THEME).toMatchObject({
      placement: 'bottom-left',
      radius_px: 24,
      display_ms: 4_000,
      motion: 'standard',
    })
    expect(DEFAULT_TAROT_OVERLAY_THEME).toEqual({
      ...DEFAULT_COMMUNITY_OVERLAY_THEME,
      radius_px: 16,
      display_ms: 5_000,
    })
  })
})

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
    expect(url.pathname).toBe('/api/live-display/public/events')
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

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe('/api/live-display/settings')
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

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe('/api/live-display/settings')
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
      '/api/live-display/settings/rotate-key'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'live-display' },
    })
  })

  it('triggers a tenant-scoped preview without using the feature command', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ content_type: 'checkin', event_id: 91 }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await triggerCommunityOverlayPreview('checkin')

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/live-display/settings/preview'
    )
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-Niibot-Action': 'live-display',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ content_type: 'checkin' }),
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

    await getCommunityOverlayTheme('key with spaces', 'checkin')

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'https://niibot.tv')
    expect(url.pathname).toBe('/api/live-display/public/theme')
    expect(url.searchParams.get('block_type')).toBe('checkin')
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

    await getCommunityOverlayThemeSettings('checkin')

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/live-display/settings/blocks/checkin/theme'
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

    await updateCommunityOverlayThemeDraft('checkin', DEFAULT_COMMUNITY_OVERLAY_THEME, 3)

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(
      '/api/live-display/settings/blocks/checkin/theme/draft'
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
    [publishCommunityOverlayTheme, '/api/live-display/settings/blocks/checkin/theme/publish'],
    [
      resetCommunityOverlayThemeDraft,
      '/api/live-display/settings/blocks/checkin/theme/reset-draft',
    ],
  ] as const)('posts a theme lifecycle action', async (action, path) => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ draft: DEFAULT_COMMUNITY_OVERLAY_THEME }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await action('checkin', 3)

    expect(new URL(String(fetchMock.mock.calls[0][0])).pathname).toBe(path)
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: {
        'X-Niibot-Action': 'live-display',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ expected_draft_version: 3 }),
    })
  })
})
