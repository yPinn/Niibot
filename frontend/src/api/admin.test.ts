import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/config', () => ({
  API_ENDPOINTS: {
    admin: {
      suspendMembership: (userId: string) => `/api/admin/memberships/${userId}/suspend`,
    },
  },
  apiFetch: vi.fn(),
}))

import { suspendMembership } from '@/api/admin'
import { apiFetch } from '@/api/config'

const mockApiFetch = apiFetch as ReturnType<typeof vi.fn>

describe('suspendMembership', () => {
  beforeEach(() => vi.clearAllMocks())

  it('posts the selected reason to the target membership', async () => {
    mockApiFetch.mockResolvedValue(new Response('{}', { status: 200 }))

    await suspendMembership('user-1', '違反使用規範')

    expect(mockApiFetch).toHaveBeenCalledWith('/api/admin/memberships/user-1/suspend', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: '違反使用規範' }),
    })
  })

  it('throws the parsed API error when suspension fails', async () => {
    mockApiFetch.mockResolvedValue(
      new Response(JSON.stringify({ detail: 'forbidden' }), {
        status: 403,
        headers: { 'Content-Type': 'application/json' },
      })
    )

    await expect(suspendMembership('user-1', '人工複查')).rejects.toThrow()
  })
})
