import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import { removeVipEntitlement } from './vip'

describe('VIP management API', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('removes an entitlement for the authenticated tenant with an explicit action header', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
    })
    vi.stubGlobal('fetch', fetchMock)

    await removeVipEntitlement('viewer/1')

    expect(requestUrl(fetchMock.mock.calls[0][0]).pathname).toBe('/api/vip/entitlements/viewer%2F1')
    expect(fetchMock.mock.calls[0][1]).toEqual({
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'X-Niibot-Action': 'vip-management',
      },
    })
  })
})
