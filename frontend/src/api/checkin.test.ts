import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import { getCheckinLeaderboard, getCheckinSettings, updateCheckinSettings } from './checkin'

describe('check-in settings API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('loads settings for the authenticated tenant', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ timezone: 'Asia/Taipei' }),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCheckinSettings()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/settings')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('loads the authenticated tenant leaderboard', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue([]),
    })
    vi.stubGlobal('fetch', fetchMock)

    await getCheckinLeaderboard()

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/leaderboard')
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
  })

  it('updates shared templates with an explicit mutation header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: vi.fn().mockResolvedValue({ timezone: 'Asia/Tokyo' }),
    })
    vi.stubGlobal('fetch', fetchMock)
    const update = {
      timezone: 'Asia/Tokyo',
      success_template: '$(@user) 第 $(count) 天',
      duplicate_template: '$(@user) 今天已簽到',
    }

    await updateCheckinSettings(update)

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/checkin/settings')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'checkin-settings',
      },
      body: JSON.stringify(update),
    })
  })
})
