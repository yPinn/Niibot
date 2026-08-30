import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/admin', () => ({
  getAdminChannels: vi.fn(),
  getAdminBotStatus: vi.fn(),
  reinstateMembership: vi.fn(),
  suspendMembership: vi.fn(),
}))
vi.mock('@/api/events', () => ({
  getRedemptionConfigs: vi.fn(),
  getTwitchRewards: vi.fn(),
  updateRedemptionConfig: vi.fn(),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() },
}))
vi.mock('./components/ActivationCard', () => ({
  ActivationCard: () => <div>授權管理內容</div>,
}))
vi.mock('./components/BotStatusPanel', () => ({
  BotStatusPanel: () => <div>Bot 設定內容</div>,
}))
vi.mock('./components/ChannelCard', () => ({
  ChannelCard: ({ ch, onSuspend }: { ch: AdminChannel; onSuspend?: SuspendHandler }) => (
    <button
      type="button"
      data-testid={`channel-${ch.id}`}
      data-membership-status={ch.membership_status}
      onClick={() => void onSuspend?.(ch, '違反使用規範')}
    >
      {ch.display_name}
    </button>
  ),
}))

import { toast } from 'sonner'

import type { AdminChannel } from '@/api/admin'
import { getAdminBotStatus, getAdminChannels, suspendMembership } from '@/api/admin'
import { getRedemptionConfigs, getTwitchRewards } from '@/api/events'
import { toastApiError } from '@/lib/toast-error'

import AdminPage from './index'

type SuspendHandler = (ch: AdminChannel, reason: string) => Promise<boolean>

const ACTIVE_CHANNEL: AdminChannel = {
  id: 'channel-1',
  name: 'streamer',
  display_name: 'Streamer',
  avatar: '',
  offline_image_url: '',
  is_live: false,
  is_enabled: true,
  mod_status: 'mod',
  is_bot: false,
  granted_scopes: [],
  missing_scopes: [],
  membership_status: 'active',
  membership_reason: null,
  owner_user_id: 'user-1',
}

const SUSPENDED_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-2',
  name: 'suspended',
  display_name: 'Suspended',
  is_enabled: false,
  membership_status: 'suspended',
  membership_reason: '人工複查',
  owner_user_id: 'user-2',
}

const BOT_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-bot',
  name: 'niibot',
  display_name: 'Niibot',
  is_bot: true,
  owner_user_id: null,
}

const mockGetChannels = getAdminChannels as ReturnType<typeof vi.fn>
const mockSuspend = suspendMembership as ReturnType<typeof vi.fn>

describe('AdminPage membership suspension', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetChannels.mockResolvedValueOnce([ACTIVE_CHANNEL])
    ;(getAdminBotStatus as ReturnType<typeof vi.fn>).mockResolvedValue(null)
    ;(getRedemptionConfigs as ReturnType<typeof vi.fn>).mockResolvedValue([])
    ;(getTwitchRewards as ReturnType<typeof vi.fn>).mockResolvedValue([])
    mockSuspend.mockResolvedValue(undefined)
  })

  it('uses an operator-first reading order with a full-width authorization region', async () => {
    render(<AdminPage />)

    expect(await screen.findByText('使用者與頻道')).toBeInTheDocument()
    expect(screen.getByText('Bot 設定內容')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '授權管理' })).toHaveTextContent('授權管理內容')
  })

  it('filters the unified user grid by membership and monitoring state', async () => {
    const user = userEvent.setup()
    mockGetChannels.mockReset()
    mockGetChannels.mockResolvedValueOnce([ACTIVE_CHANNEL, SUSPENDED_CHANNEL, BOT_CHANNEL])
    render(<AdminPage />)

    expect(await screen.findByTestId('channel-channel-1')).toBeInTheDocument()
    expect(screen.getByTestId('channel-channel-2')).toBeInTheDocument()
    expect(screen.queryByTestId('channel-channel-bot')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /全部\s*2/ })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /已停權\s*1/ }))

    expect(screen.queryByTestId('channel-channel-1')).not.toBeInTheDocument()
    expect(screen.getByTestId('channel-channel-2')).toBeInTheDocument()
  })

  it('keeps the user cards in the established responsive auto-fill grid', async () => {
    render(<AdminPage />)

    const channel = await screen.findByTestId('channel-channel-1')
    expect(channel.parentElement).toHaveClass('grid-cols-[repeat(auto-fill,minmax(200px,1fr))]')
  })

  it('keeps the successful suspension when the background refresh fails', async () => {
    const user = userEvent.setup()
    mockGetChannels.mockRejectedValueOnce(new Error('refresh failed'))
    render(<AdminPage />)

    const channel = await screen.findByTestId('channel-channel-1')
    await user.click(channel)

    await waitFor(() => {
      expect(mockSuspend).toHaveBeenCalledWith('user-1', '違反使用規範')
      expect(screen.getByTestId('channel-channel-1')).toHaveAttribute(
        'data-membership-status',
        'suspended'
      )
    })
    expect(toast.success).toHaveBeenCalledWith('Streamer 已停權')
    expect(toastApiError).not.toHaveBeenCalled()
  })
})
