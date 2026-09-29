import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import type { BotTokenInfo } from '@/api/admin'
import { createSystemBotResetInvite } from '@/api/botAccounts'

import { BotStatusPanel } from './BotStatusPanel'

vi.mock('@/api/botAccounts', () => ({ createSystemBotResetInvite: vi.fn() }))
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }))

const mockCreateReset = createSystemBotResetInvite as MockedFunction<
  typeof createSystemBotResetInvite
>

const BOT: BotTokenInfo = {
  id: 'bot-test',
  name: 'niibot_',
  display_name: 'Niibot',
  avatar: '',
  status: 'ok',
  granted_scopes: ['user:bot'],
  missing_scopes: [],
}

function renderPanel(bot: BotTokenInfo | null = BOT) {
  return render(
    <BotStatusPanel
      bot={bot}
      botLoading={false}
      redemptionLoading={false}
      rewardsLoading={false}
      niibotAuth={{
        id: 1,
        channel_id: 'channel-1',
        action_type: 'niibot_auth',
        reward_name: 'Niibot 使用資格',
        reward_id: 'reward-1',
        enabled: true,
        first_message: '',
        first_announce_color: 'primary',
      }}
      twitchRewards={[
        {
          id: 'reward-1',
          title: 'Niibot 使用資格',
          cost: 500,
          is_enabled: true,
          is_paused: false,
          is_in_stock: true,
          should_redemptions_skip_request_queue: false,
          max_per_stream: null,
          max_per_user_per_stream: null,
        },
      ]}
      onRewardSelect={vi.fn()}
      onAuthToggle={vi.fn()}
    />
  )
}

describe('BotStatusPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockCreateReset.mockResolvedValue({
      invite_id: 'invite-1',
      public_url: 'https://niibot.test/bot-invite/opaque?nonce=state-nonce',
      expires_at: '2026-08-31T12:00:00Z',
    })
  })

  it.each([
    ['ok', '已就緒', 'Bot 已可正常使用。', '更新授權'],
    ['missing', '權限不足', '部分功能暫時無法使用，請重新授權。', '補充授權'],
    ['no_token', '尚未授權', '完成授權後，Niibot 才能以這個帳號運作。', '連結帳號'],
  ] as const)('shows actionable copy for the %s state', (status, label, description, action) => {
    renderPanel({
      ...BOT,
      status,
      missing_scopes: status === 'missing' ? ['user:write:chat'] : [],
    })

    expect(screen.getByText(label)).toBeInTheDocument()
    expect(screen.getByText(description)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: action })).toBeInTheDocument()
  })

  it('keeps one account summary and hides provider implementation detail', () => {
    renderPanel({
      ...BOT,
      status: 'missing',
      missing_scopes: ['user:write:chat', 'moderator:manage:banned_users'],
    })

    expect(screen.getAllByText('Niibot')).toHaveLength(1)
    expect(screen.getByText('@niibot_')).toBeInTheDocument()
    expect(screen.queryByText('user:write:chat')).not.toBeInTheDocument()
    expect(screen.queryByText('moderator:manage:banned_users')).not.toBeInTheDocument()
    expect(screen.queryByText(/Token/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/no token|ready|missing/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/新增帳號/)).not.toBeInTheDocument()
  })

  it('creates one expected-account invite and replaces the action with a safe link', async () => {
    const user = userEvent.setup()
    renderPanel()

    await user.click(screen.getByRole('button', { name: '更新授權' }))

    await waitFor(() => expect(mockCreateReset).toHaveBeenCalledOnce())
    expect(screen.getByText('請使用 Niibot 完成授權；連結只能使用一次。')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '開啟授權頁' })).toHaveAttribute(
      'href',
      'https://niibot.test/bot-invite/opaque?nonce=state-nonce'
    )
    expect(screen.queryByDisplayValue(/\/bot-invite\/opaque/)).not.toBeInTheDocument()
  })

  it('prevents duplicate invite creation while the request is pending', async () => {
    let resolveInvite:
      ((value: Awaited<ReturnType<typeof createSystemBotResetInvite>>) => void) | null = null
    mockCreateReset.mockImplementation(
      () =>
        new Promise(resolve => {
          resolveInvite = resolve
        })
    )
    const user = userEvent.setup()
    renderPanel()

    const action = screen.getByRole('button', { name: '更新授權' })
    await user.click(action)

    expect(action).toBeDisabled()
    expect(mockCreateReset).toHaveBeenCalledOnce()

    resolveInvite?.({
      invite_id: 'invite-1',
      public_url: 'https://niibot.test/bot-invite/opaque?nonce=state-nonce',
      expires_at: '2026-08-31T12:00:00Z',
    })
  })

  it('uses user-facing copy for invite errors and the access reward setting', async () => {
    mockCreateReset.mockRejectedValueOnce(new Error('provider detail'))
    const user = userEvent.setup()
    renderPanel()

    expect(screen.getByText('使用資格獎勵')).toBeInTheDocument()
    expect(screen.getByText('觀眾兌換後，可在下次登入取得 Niibot 使用資格。')).toBeInTheDocument()
    expect(screen.getByRole('switch', { name: '啟用使用資格兌換' })).toBeChecked()
    expect(screen.queryByText('niibot_auth')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '更新授權' }))

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('建立 Bot 授權連結失敗'))
  })
})
