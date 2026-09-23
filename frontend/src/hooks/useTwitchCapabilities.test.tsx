import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/botAccounts', () => ({ getTwitchCapabilities: vi.fn() }))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 'channel-1' }, isInitialized: true }),
}))

import { getTwitchCapabilities } from '@/api/botAccounts'

import { useTwitchCapabilities } from './useTwitchCapabilities'

describe('useTwitchCapabilities', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getTwitchCapabilities).mockResolvedValue({
      broadcaster_status: 'valid',
      bot_status: 'valid',
      bot_user_id: 'bot-1',
      capabilities: [
        {
          key: 'channel_points',
          label: 'Channel Points',
          credential: 'broadcaster',
          available: false,
          missing_scopes: ['channel:read:redemptions'],
          core: false,
        },
      ],
    })
  })

  it('exposes one feature lock without treating the whole credential as invalid', async () => {
    const { result } = renderHook(() => useTwitchCapabilities())

    await waitFor(() => expect(result.current.loading).toBe(false))

    expect(result.current.snapshot?.broadcaster_status).toBe('valid')
    expect(result.current.capability('channel_points')).toMatchObject({ available: false })
    expect(result.current.isAvailable('channel_points')).toBe(false)
    expect(result.current.isAvailable('moderator_management')).toBe(false)
  })
})
