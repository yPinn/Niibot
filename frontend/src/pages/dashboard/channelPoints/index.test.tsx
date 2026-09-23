import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const capabilityMocks = vi.hoisted(() => ({
  isAvailable: vi.fn(() => true),
  capability: vi.fn(() => null),
}))

vi.mock('@/api/events', () => ({
  getEventCatalog: vi.fn(),
  getEventConfigs: vi.fn(),
  getRedemptionConfigs: vi.fn(),
  getTwitchRewards: vi.fn(),
  updateRedemptionConfig: vi.fn(),
  updateFirstRedemptionSettings: vi.fn(),
}))
vi.mock('@/api/checkin', () => ({
  applyCheckinImport: vi.fn(),
  clearCheckinData: vi.fn(),
  exportCheckinData: vi.fn(),
  getCheckinDataSummary: vi.fn(),
  getCheckinLeaderboard: vi.fn(),
  getCheckinSettings: vi.fn(),
  previewCheckinImport: vi.fn(),
  updateCheckinSettings: vi.fn(),
}))
vi.mock('@/api/vip', () => ({
  getVipState: vi.fn(),
  initializeVipTracking: vi.fn(),
  updateVipSlotLimit: vi.fn(),
  syncVipState: vi.fn(),
  upsertVipRule: vi.fn(),
  adoptExternalVip: vi.fn(),
  keepExternalVip: vi.fn(),
  adjustVipEntitlement: vi.fn(),
  removeVipEntitlement: vi.fn(),
  setVipRulesEnabled: vi.fn(),
}))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isAffiliate: true }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/hooks/useTwitchCapabilities', () => ({
  useTwitchCapabilities: () => ({
    loading: false,
    error: false,
    snapshot: null,
    refresh: vi.fn(),
    ...capabilityMocks,
  }),
}))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { getCheckinLeaderboard, getCheckinSettings, updateCheckinSettings } from '@/api/checkin'
import {
  getEventCatalog,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
  updateFirstRedemptionSettings,
  updateRedemptionConfig,
} from '@/api/events'
import { adjustVipEntitlement, getVipState, removeVipEntitlement, upsertVipRule } from '@/api/vip'
import { toastApiError } from '@/lib/toast-error'

import ChannelPoints from './index'

const CHECKIN = {
  id: 8,
  channel_id: 'channel-1',
  action_type: 'checkin',
  reward_name: '每日簽到',
  reward_id: 'reward-checkin',
  enabled: true,
  first_message: '$(@user) 恭喜你搶到沙發！',
  first_announce_color: 'primary',
}

const GAME_QUEUE = {
  ...CHECKIN,
  id: 9,
  action_type: 'game_queue',
  reward_name: '遊戲入場券',
  reward_id: 'reward-game',
}

const FIRST = {
  ...CHECKIN,
  id: 10,
  action_type: 'first',
  reward_name: '我先來的',
  reward_id: 'reward-first',
}

const VIDEO_QUEUE = {
  ...CHECKIN,
  id: 11,
  action_type: 'video_queue',
  reward_name: '好看愛看',
  reward_id: 'reward-video',
}

const VIP = {
  ...CHECKIN,
  id: 12,
  action_type: 'vip',
  reward_name: '酷酷的俗頭',
  reward_id: 'reward-vip',
}

const REWARDS = [
  {
    id: 'reward-checkin',
    title: '每日簽到',
    cost: 10,
    is_enabled: true,
    is_paused: false,
    is_in_stock: true,
    should_redemptions_skip_request_queue: true,
    max_per_stream: 100,
    max_per_user_per_stream: 1,
  },
  {
    id: 'reward-game',
    title: '遊戲入場券',
    cost: 1000,
    is_enabled: true,
    is_paused: false,
    is_in_stock: true,
    should_redemptions_skip_request_queue: false,
    max_per_stream: null,
    max_per_user_per_stream: 1,
  },
]

const CHECKIN_SETTINGS = {
  channel_id: 'channel-1',
  timezone: 'Asia/Taipei',
  success_template: '$(@user) 簽到成功，累積 $(count) 天！',
  duplicate_template: '$(@user) 今天已經簽到過了，目前累積 $(count) 天！',
  reply_delay_seconds: 0,
  created_at: '2026-08-31T00:00:00Z',
  updated_at: '2026-08-31T00:00:00Z',
}

const CHECKIN_LEADERBOARD = [
  {
    rank: 1,
    user_id: 'viewer-1',
    username: 'alice',
    display_name: 'Alice',
    total_days: 12,
    last_checkin_date: '2026-08-31',
  },
  {
    rank: 2,
    user_id: 'viewer-2',
    username: 'bob',
    display_name: null,
    total_days: 8,
    last_checkin_date: '2026-08-30',
  },
]

const VIP_STATE = {
  settings: {
    channel_id: 'channel-1',
    slot_limit: 10,
    tracking_started_at: '2026-08-31T00:00:00Z',
    last_full_sync_at: '2026-08-31T00:00:00Z',
    created_at: '2026-08-31T00:00:00Z',
    updated_at: '2026-08-31T00:00:00Z',
  },
  rules: [
    {
      id: 1,
      channel_id: 'channel-1',
      reward_id: 'reward-vip',
      reward_name_snapshot: '酷酷的俗頭',
      duration_months: 3,
      is_permanent: false,
      enabled: true,
    },
  ],
  entitlements: [],
  redemptions: [],
}

describe('Channel Points page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capabilityMocks.isAvailable.mockReturnValue(true)
    capabilityMocks.capability.mockReturnValue(null)
    vi.mocked(getRedemptionConfigs).mockResolvedValue([CHECKIN, GAME_QUEUE])
    vi.mocked(getTwitchRewards).mockResolvedValue(REWARDS)
    vi.mocked(updateRedemptionConfig).mockImplementation(async (actionType, update) => ({
      ...(actionType === 'checkin' ? CHECKIN : GAME_QUEUE),
      ...update,
    }))
    vi.mocked(updateFirstRedemptionSettings).mockImplementation(async update => ({
      ...FIRST,
      first_message: update.message,
      first_announce_color: update.announce_color,
    }))
    vi.mocked(getCheckinSettings).mockResolvedValue(CHECKIN_SETTINGS)
    vi.mocked(getCheckinLeaderboard).mockResolvedValue(CHECKIN_LEADERBOARD)
    vi.mocked(updateCheckinSettings).mockImplementation(async update => ({
      ...CHECKIN_SETTINGS,
      ...update,
    }))
    vi.mocked(getVipState).mockResolvedValue(VIP_STATE)
    vi.mocked(upsertVipRule).mockImplementation(async (_rewardId, update) => ({
      ...VIP_STATE.rules[0],
      ...update,
    }))
    vi.mocked(adjustVipEntitlement).mockImplementation(async (_userId, _months, isPermanent) => ({
      id: 1,
      channel_id: 'channel-1',
      user_id: 'user-1',
      user_login: 'alice',
      display_name: 'Alice',
      source: 'managed',
      status: 'active',
      granted_at: '2026-08-31T00:00:00Z',
      expires_at: isPermanent ? null : '2099-01-01T00:00:00Z',
      is_permanent: isPermanent,
      last_reward_rule_id: 1,
      last_synced_at: '2026-08-31T00:00:00Z',
    }))
  })

  it('does not call Twitch reward APIs when Channel Points scope is locked', async () => {
    capabilityMocks.isAvailable.mockImplementation(key => key !== 'channel_points')
    capabilityMocks.capability.mockImplementation(key =>
      key === 'channel_points'
        ? {
            key: 'channel_points',
            label: 'Channel Points',
            credential: 'broadcaster',
            available: false,
            missing_scopes: ['channel:read:redemptions'],
            core: false,
          }
        : null
    )

    render(<ChannelPoints />)

    expect(
      await screen.findByText('Channel Points目前保持鎖定，其他已授權功能不受影響。')
    ).toBeInTheDocument()
    expect(getTwitchRewards).not.toHaveBeenCalled()
    expect(getVipState).not.toHaveBeenCalled()
    expect(screen.getByText('需要 Twitch 功能授權')).toBeInTheDocument()
  })

  it('owns reward-to-action mappings and includes daily check-in', async () => {
    render(<ChannelPoints />)

    expect(await screen.findByRole('heading', { name: 'Channel Points' })).toBeInTheDocument()
    expect(screen.getByText('頻道點數動作')).toBeInTheDocument()
    expect(screen.getByText('每日簽到')).toBeInTheDocument()
    expect(screen.getByText('遊戲排隊券')).toBeInTheDocument()
    expect(getEventConfigs).not.toHaveBeenCalled()
    expect(getEventCatalog).not.toHaveBeenCalled()
  })

  it('separates enabled state from action-specific operations', async () => {
    render(<ChannelPoints />)

    const checkinRow = await screen.findByRole('row', { name: /每日簽到/ })

    expect(screen.getAllByRole('columnheader').map(header => header.textContent?.trim())).toEqual([
      '動作',
      'Twitch 獎勵',
      '狀態',
      '操作',
    ])
    expect(within(checkinRow).getAllByRole('cell')).toHaveLength(4)
    expect(within(checkinRow).getByRole('switch', { name: '啟用 每日簽到' })).toBeInTheDocument()
    expect(within(checkinRow).getByRole('button', { name: '編輯每日簽到設定' })).toBeInTheDocument()
  })

  it('lists default mappings before actions with additional workflows', async () => {
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([
      VIP,
      CHECKIN,
      VIDEO_QUEUE,
      FIRST,
      GAME_QUEUE,
    ])
    render(<ChannelPoints />)

    const rows = await screen.findAllByRole('row')
    const actionLabels = rows.slice(1).map(row => within(row).getAllByRole('cell')[0].textContent)

    expect(actionLabels).toEqual([
      expect.stringContaining('本日頭香'),
      expect.stringContaining('遊戲排隊券'),
      expect.stringContaining('播放清單'),
      expect.stringContaining('每日簽到'),
      expect.stringContaining('VIP 授予'),
    ])
  })

  it('keeps reward id as the mapping value', async () => {
    const user = userEvent.setup()
    const replacement = { ...REWARDS[0], id: 'reward-second', title: '第二個簽到獎勵' }
    vi.mocked(getTwitchRewards).mockResolvedValueOnce([...REWARDS, replacement])
    render(<ChannelPoints />)

    const select = await screen.findByRole('combobox', { name: '每日簽到的 Twitch 獎勵' })
    await user.click(select)
    await user.click(screen.getByRole('option', { name: /第二個簽到獎勵/ }))

    await waitFor(() =>
      expect(updateRedemptionConfig).toHaveBeenCalledWith('checkin', {
        reward_id: 'reward-second',
        reward_name: '第二個簽到獎勵',
        enabled: true,
      })
    )
  })

  it('edits tenant check-in settings separately from the reward mapping', async () => {
    const user = userEvent.setup()
    render(<ChannelPoints />)

    expect(getCheckinSettings).not.toHaveBeenCalled()
    expect(getCheckinLeaderboard).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('button', { name: '編輯每日簽到設定' }))

    expect(await screen.findByRole('heading', { name: 'Check-in settings' })).toBeInTheDocument()
    expect(screen.getByText(/聊天指令與 Twitch 點數簽到共用/)).toBeInTheDocument()
    expect(screen.getByText('補償畫面比聊天室晚顯示的秒數；預設 5 秒。')).toBeInTheDocument()
    expect(getCheckinSettings).toHaveBeenCalledOnce()
    expect(getCheckinLeaderboard).toHaveBeenCalledOnce()
    const todayOrderVariable = screen.getByRole('button', { name: '$(today_order)' })
    expect(todayOrderVariable).toBeInTheDocument()
    await user.hover(todayOrderVariable)
    expect(screen.getByText('今天第幾位完成簽到')).toBeInTheDocument()

    const leaderboard = screen.getByRole('region', { name: '簽到排行榜' })
    const [firstPlace] = within(leaderboard).getAllByRole('listitem')
    expect(firstPlace).toHaveTextContent('Alice')
    expect(firstPlace).not.toHaveTextContent('@alice')
    expect(firstPlace).toHaveTextContent('12 天')
    expect(within(leaderboard).getByText('bob')).toBeInTheDocument()

    await user.click(screen.getByRole('combobox', { name: '時區' }))
    await user.click(screen.getByRole('option', { name: /東京/ }))
    await user.click(screen.getByRole('button', { name: '儲存設定' }))

    await waitFor(() =>
      expect(updateCheckinSettings).toHaveBeenCalledWith({
        timezone: 'Asia/Tokyo',
        success_template: CHECKIN_SETTINGS.success_template,
        duplicate_template: CHECKIN_SETTINGS.duplicate_template,
        reply_delay_seconds: CHECKIN_SETTINGS.reply_delay_seconds,
      })
    )
  })

  it('edits the 頭香 announcement message separately from the reward mapping', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([FIRST, CHECKIN])
    render(<ChannelPoints />)

    const firstRow = await screen.findByRole('row', { name: /本日頭香/ })
    await user.click(within(firstRow).getByRole('button', { name: '編輯本日頭香設定' }))

    expect(await screen.findByRole('heading', { name: '本日頭香設定' })).toBeInTheDocument()

    const message = screen.getByRole('textbox')
    await user.clear(message)
    await user.type(message, '$(@user) 手速真快！')
    await user.click(screen.getByRole('button', { name: '儲存設定' }))

    await waitFor(() =>
      expect(updateFirstRedemptionSettings).toHaveBeenCalledWith({
        message: '$(@user) 手速真快！',
        announce_color: 'primary',
      })
    )
  })

  it('shows a dedicated empty state when nobody has checked in', async () => {
    const user = userEvent.setup()
    vi.mocked(getCheckinLeaderboard).mockResolvedValueOnce([])
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '編輯每日簽到設定' }))

    const leaderboard = await screen.findByRole('region', { name: '簽到排行榜' })
    expect(within(leaderboard).getByText('尚無簽到紀錄')).toBeInTheDocument()
  })

  it('keeps settings editable when the leaderboard fails to load', async () => {
    const user = userEvent.setup()
    vi.mocked(getCheckinLeaderboard).mockRejectedValueOnce(new Error('offline'))
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '編輯每日簽到設定' }))

    expect(await screen.findByText('簽到排行榜載入失敗')).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: '時區' })).toHaveTextContent('台北')
    await user.click(screen.getByRole('button', { name: '儲存設定' }))
    await waitFor(() => expect(updateCheckinSettings).toHaveBeenCalledOnce())
  })

  it('opens the timed VIP workflow from the separate operation column', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP, CHECKIN])
    render(<ChannelPoints />)

    const vipRow = await screen.findByRole('row', { name: /VIP 授予/ })
    await user.click(within(vipRow).getByRole('button', { name: '管理VIP 授予設定' }))

    expect(await screen.findByRole('heading', { name: 'VIP management' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'VIP 使用量' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Reward 期限規則' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '當前 VIP 名單' })).toBeInTheDocument()
    expect(getVipState).toHaveBeenCalledTimes(2)
  })

  it('edits an existing VIP reward duration and enabled state', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP])
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '管理VIP 授予設定' }))

    await user.click(await screen.findByRole('combobox', { name: '酷酷的俗頭 的期限' }))
    await user.click(screen.getByRole('option', { name: '6 個月' }))
    await waitFor(() =>
      expect(upsertVipRule).toHaveBeenCalledWith('reward-vip', {
        duration_months: 6,
        is_permanent: false,
        enabled: true,
      })
    )

    await user.click(screen.getByRole('switch', { name: '啟用 酷酷的俗頭' }))
    await waitFor(() =>
      expect(upsertVipRule).toHaveBeenCalledWith('reward-vip', {
        duration_months: 3,
        is_permanent: false,
        enabled: false,
      })
    )
  })

  it('keeps VIP status concise and reveals per-user adjustment only when requested', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP])
    vi.mocked(getVipState).mockResolvedValue({
      ...VIP_STATE,
      entitlements: [
        {
          id: 1,
          channel_id: 'channel-1',
          user_id: 'user-1',
          user_login: 'alice',
          display_name: 'Alice',
          source: 'managed',
          status: 'active',
          granted_at: '2026-08-31T00:00:00Z',
          expires_at: '2099-01-01T00:00:00Z',
          is_permanent: false,
          last_reward_rule_id: 1,
          last_synced_at: '2026-08-31T00:00:00Z',
        },
        {
          id: 2,
          channel_id: 'channel-1',
          user_id: 'user-2',
          user_login: 'bob',
          display_name: 'Bob',
          source: 'external_baseline',
          status: 'active',
          granted_at: null,
          expires_at: null,
          is_permanent: false,
          last_reward_rule_id: null,
          last_synced_at: '2026-08-31T00:00:00Z',
        },
      ],
    })
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '管理VIP 授予設定' }))

    const usage = await screen.findByRole('region', { name: 'VIP 使用量' })
    expect(usage).toHaveTextContent(/目前\s*2\s*位 VIP/)
    expect(screen.queryByText('可用')).not.toBeInTheDocument()
    expect(screen.queryByText('Managed')).not.toBeInTheDocument()
    expect(screen.queryByText('External')).not.toBeInTheDocument()
    expect(screen.queryByText(/上次完整同步/)).not.toBeInTheDocument()
    expect(screen.getByText('獎勵')).toBeInTheDocument()
    expect(screen.getByText('外部')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: '調整 Alice 期限' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '調整 Alice 期限' }))
    const duration = screen.getByRole('combobox', { name: '調整 Alice 期限' })
    await user.click(duration)
    await user.click(screen.getByRole('option', { name: '6 個月' }))
    await user.click(screen.getByRole('button', { name: '套用' }))

    await waitFor(() => expect(adjustVipEntitlement).toHaveBeenCalledWith('user-1', 6, false))
  })

  it('shows the Twitch VIP badge before the username and confirms manual removal', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP])
    vi.mocked(getVipState).mockResolvedValue({
      ...VIP_STATE,
      entitlements: [
        {
          id: 1,
          channel_id: 'channel-1',
          user_id: 'user-1',
          user_login: 'alice',
          display_name: 'Alice',
          source: 'managed',
          status: 'active',
          granted_at: '2026-08-31T00:00:00Z',
          expires_at: '2099-01-01T00:00:00Z',
          is_permanent: false,
          last_reward_rule_id: 1,
          last_synced_at: '2026-08-31T00:00:00Z',
        },
      ],
    })
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '管理VIP 授予設定' }))

    const vipBadge = await screen.findByRole('img', { name: 'VIP' })
    const username = screen.getByText('Alice')
    expect(vipBadge).toHaveAttribute('width', '18')
    expect(
      vipBadge.compareDocumentPosition(username) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()

    await user.click(screen.getByRole('button', { name: '移除 Alice 的 VIP' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('移除 Alice 的 VIP？')
    expect(removeVipEntitlement).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '取消' }))
    expect(removeVipEntitlement).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '移除 Alice 的 VIP' }))
    await user.click(screen.getByRole('button', { name: '移除 VIP' }))

    await waitFor(() => expect(removeVipEntitlement).toHaveBeenCalledWith('user-1'))
    await waitFor(() => expect(getVipState).toHaveBeenCalledTimes(3))
  })

  it('keeps the VIP visible when Twitch rejects manual removal', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP])
    vi.mocked(removeVipEntitlement).mockRejectedValueOnce(new Error('offline'))
    vi.mocked(getVipState).mockResolvedValue({
      ...VIP_STATE,
      entitlements: [
        {
          id: 1,
          channel_id: 'channel-1',
          user_id: 'user-1',
          user_login: 'alice',
          display_name: 'Alice',
          source: 'external_event',
          status: 'active',
          granted_at: null,
          expires_at: null,
          is_permanent: false,
          last_reward_rule_id: null,
          last_synced_at: '2026-08-31T00:00:00Z',
        },
      ],
    })
    render(<ChannelPoints />)

    await user.click(await screen.findByRole('button', { name: '管理VIP 授予設定' }))
    await user.click(await screen.findByRole('button', { name: '移除 Alice 的 VIP' }))
    await user.click(screen.getByRole('button', { name: '移除 VIP' }))

    await waitFor(() => expect(toastApiError).toHaveBeenCalled())
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(getVipState).toHaveBeenCalledTimes(2)
  })
})
