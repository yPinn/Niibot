import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import { createSystemBotResetInvite } from '@/api/botAccounts'

import { BotStatusPanel } from './BotStatusPanel'

vi.mock('@/api/botAccounts', () => ({ createSystemBotResetInvite: vi.fn() }))
const mockCreateReset = createSystemBotResetInvite as MockedFunction<
  typeof createSystemBotResetInvite
>

describe('BotStatusPanel reset invite', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateReset.mockResolvedValue({
      invite_id: 'invite-1',
      public_url: 'https://niibot.test/bot-invite/opaque?nonce=state-nonce',
      expires_at: '2026-08-31T12:00:00Z',
    })
  })

  it('replaces local token reset scripts with an expected-account invite URL', async () => {
    const user = userEvent.setup()
    render(
      <BotStatusPanel
        bot={{
          id: 'bot-test',
          name: 'niibot_',
          display_name: 'Niibot',
          avatar: '',
          status: 'ok',
          granted_scopes: ['user:bot'],
          missing_scopes: [],
        }}
        botLoading={false}
        redemptionLoading
        rewardsLoading
        niibotAuth={null}
        twitchRewards={[]}
        onRewardSelect={vi.fn()}
        onAuthToggle={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: '更新 Niibot Token' }))

    await waitFor(() => expect(mockCreateReset).toHaveBeenCalledOnce())
    expect(screen.getByDisplayValue(/\/bot-invite\/opaque/)).toBeInTheDocument()
  })
})
