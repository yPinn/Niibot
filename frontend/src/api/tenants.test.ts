import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getTenants } from '@/api/tenants'

describe('getTenants', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('loads server-resolved tenant roles and capabilities with credentials', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({
          tenants: [
            {
              channel_id: '123',
              channel_name: 'alice',
              display_name: 'Alice',
              enabled: true,
              role: 'manager',
              capabilities: ['edit_operations', 'switch_bot', 'toggle_bot'],
            },
          ],
        }),
        { status: 200 }
      )
    )

    const tenants = await getTenants({ forceRefresh: true })

    expect(tenants[0].role).toBe('manager')
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/tenants'),
      expect.objectContaining({ credentials: 'include' })
    )
  })

  it('throws instead of treating an authorization failure as an empty list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'TENANT.ACCOUNT_LOCKED' } }), {
        status: 403,
      })
    )

    await expect(getTenants({ forceRefresh: true })).rejects.toThrow()
  })
})
