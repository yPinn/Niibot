import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/events', () => ({
  getEventCatalog: vi.fn(),
  getEventConfigs: vi.fn(),
  getRedemptionConfigs: vi.fn(),
  getTwitchRewards: vi.fn(),
  updateRedemptionConfig: vi.fn(),
}))
vi.mock('@/api/checkin', () => ({
  getCheckinSettings: vi.fn(),
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
  setVipRulesEnabled: vi.fn(),
}))
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ isAffiliate: true }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { getCheckinSettings, updateCheckinSettings } from '@/api/checkin'
import {
  getEventCatalog,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
  updateRedemptionConfig,
} from '@/api/events'
import { getVipState, upsertVipRule } from '@/api/vip'

import ChannelPoints from './index'

const CHECKIN = {
  id: 8,
  channel_id: 'channel-1',
  action_type: 'checkin',
  reward_name: '每日簽到',
  reward_id: 'reward-checkin',
  enabled: true,
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
  created_at: '2026-08-31T00:00:00Z',
  updated_at: '2026-08-31T00:00:00Z',
}

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
    vi.mocked(getRedemptionConfigs).mockResolvedValue([CHECKIN, GAME_QUEUE])
    vi.mocked(getTwitchRewards).mockResolvedValue(REWARDS)
    vi.mocked(updateRedemptionConfig).mockImplementation(async (actionType, update) => ({
      ...(actionType === 'checkin' ? CHECKIN : GAME_QUEUE),
      ...update,
    }))
    vi.mocked(getCheckinSettings).mockResolvedValue(CHECKIN_SETTINGS)
    vi.mocked(updateCheckinSettings).mockImplementation(async update => ({
      ...CHECKIN_SETTINGS,
      ...update,
    }))
    vi.mocked(getVipState).mockResolvedValue(VIP_STATE)
    vi.mocked(upsertVipRule).mockImplementation(async (_rewardId, update) => ({
      ...VIP_STATE.rules[0],
      ...update,
    }))
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
    await user.click(await screen.findByRole('button', { name: '編輯每日簽到設定' }))

    expect(await screen.findByRole('heading', { name: 'Check-in settings' })).toBeInTheDocument()
    expect(screen.getByText(/聊天指令與 Twitch 點數簽到共用/)).toBeInTheDocument()
    expect(getCheckinSettings).toHaveBeenCalledOnce()

    const timezone = screen.getByRole('textbox', { name: '時區' })
    await user.clear(timezone)
    await user.type(timezone, 'Asia/Tokyo')
    await user.click(screen.getByRole('button', { name: '儲存設定' }))

    await waitFor(() =>
      expect(updateCheckinSettings).toHaveBeenCalledWith({
        timezone: 'Asia/Tokyo',
        success_template: CHECKIN_SETTINGS.success_template,
        duplicate_template: CHECKIN_SETTINGS.duplicate_template,
      })
    )
  })

  it('opens the timed VIP workflow from the separate operation column', async () => {
    const user = userEvent.setup()
    vi.mocked(getRedemptionConfigs).mockResolvedValueOnce([VIP, CHECKIN])
    render(<ChannelPoints />)

    const vipRow = await screen.findByRole('row', { name: /VIP 授予/ })
    await user.click(within(vipRow).getByRole('button', { name: '管理VIP 授予設定' }))

    expect(await screen.findByRole('heading', { name: 'VIP management' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '容量與同步' })).toBeInTheDocument()
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
})
