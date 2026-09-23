import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api/twitchOAuth', () => ({ openTwitchOAuth: vi.fn().mockResolvedValue(undefined) }))
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

import { openTwitchOAuth } from '@/api/twitchOAuth'

import { TwitchCapabilityAlert } from './TwitchCapabilityAlert'

describe('TwitchCapabilityAlert', () => {
  it('offers a local authorization action for only the unavailable capabilities', async () => {
    render(
      <TwitchCapabilityAlert
        capabilities={[
          {
            key: 'channel_points',
            label: 'Channel Points',
            credential: 'broadcaster',
            available: false,
            missing_scopes: ['channel:read:redemptions'],
            core: false,
          },
        ]}
      />
    )

    expect(screen.getByText(/Channel Points/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '更新 Twitch 授權' }))
    expect(openTwitchOAuth).toHaveBeenCalledOnce()
  })

  it('renders nothing when every capability is available', () => {
    const { container } = render(
      <TwitchCapabilityAlert
        capabilities={[
          {
            key: 'vip_management',
            label: 'VIP 管理',
            credential: 'broadcaster',
            available: true,
            missing_scopes: [],
            core: false,
          },
        ]}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })
})
