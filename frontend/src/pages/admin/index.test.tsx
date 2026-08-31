import { render, screen, waitFor, within } from '@testing-library/react'
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

const ISSUE_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-issue',
  name: 'scopeissue',
  display_name: 'Scope Issue',
  missing_scopes: ['moderator:read:followers'],
  owner_user_id: 'user-issue',
}

const PAUSED_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-paused',
  name: 'paused',
  display_name: 'Paused',
  is_enabled: false,
  owner_user_id: 'user-paused',
}

const PENDING_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-pending',
  name: 'pending',
  display_name: 'Pending',
  is_enabled: false,
  membership_status: 'pending',
  owner_user_id: 'user-pending',
}

const LIVE_HEALTHY_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-live',
  name: 'livehealthy',
  display_name: 'Live Healthy',
  is_live: true,
  owner_user_id: 'user-live',
}

const ALPHA_HEALTHY_CHANNEL: AdminChannel = {
  ...ACTIVE_CHANNEL,
  id: 'channel-alpha',
  name: 'alphahealthy',
  display_name: 'Alpha Healthy',
  owner_user_id: 'user-alpha',
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

    expect(
      await screen.findByRole('heading', { name: '使用者與頻道', level: 2 })
    ).toBeInTheDocument()
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

  it('groups channels in a stable frequency-first category order', async () => {
    mockGetChannels.mockReset()
    mockGetChannels.mockResolvedValueOnce([
      SUSPENDED_CHANNEL,
      ACTIVE_CHANNEL,
      PAUSED_CHANNEL,
      ISSUE_CHANNEL,
      PENDING_CHANNEL,
      LIVE_HEALTHY_CHANNEL,
      ALPHA_HEALTHY_CHANNEL,
    ])
    render(<AdminPage />)

    await screen.findByTestId('channel-channel-1')

    expect(
      screen.getAllByRole('heading', { level: 3 }).map(heading => heading.textContent)
    ).toEqual(['正常監聽', '需處理', '待審核', '監控暫停', '已停權'])

    const healthyGroup = screen.getByRole('region', { name: '正常監聽' })
    const channelNames = (regionName: string) =>
      within(screen.getByRole('region', { name: regionName }))
        .getAllByTestId(/^channel-/)
        .map(channel => channel.textContent)

    expect(
      within(healthyGroup)
        .getAllByTestId(/^channel-/)
        .map(channel => channel.textContent)
    ).toEqual(['Live Healthy', 'Alpha Healthy', 'Streamer'])
    expect(channelNames('需處理')).toEqual(['Scope Issue'])
    expect(channelNames('待審核')).toEqual(['Pending'])
    expect(channelNames('監控暫停')).toEqual(['Paused'])
    expect(channelNames('已停權')).toEqual(['Suspended'])
  })

  it('omits empty groups from the all view but keeps their filters available', async () => {
    const user = userEvent.setup()
    render(<AdminPage />)

    await screen.findByTestId('channel-channel-1')

    expect(screen.getByRole('region', { name: '正常監聽' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '已停權' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /已停權\s*0/ }))

    expect(screen.getByRole('region', { name: '已停權' })).toHaveTextContent('目前沒有已停權的頻道')
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
