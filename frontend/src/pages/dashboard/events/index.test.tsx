import { render, screen, waitFor } from '@testing-library/react'
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
  toggleEventConfig: vi.fn(),
  updateEventConfig: vi.fn(),
  updateRedemptionConfig: vi.fn(),
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

import {
  getEventCatalog,
  getEventConfigs,
  getRedemptionConfigs,
  getTwitchRewards,
} from '@/api/events'

import Events from './index'

describe('Events page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    capabilityMocks.isAvailable.mockReturnValue(true)
    capabilityMocks.capability.mockReturnValue(null)
    vi.mocked(getEventConfigs).mockResolvedValue([
      {
        id: 1,
        channel_id: 'channel-1',
        event_type: 'follow',
        message_template: '感謝 $(user) 的追隨！',
        enabled: true,
        options: {},
        trigger_count: 2,
      },
    ])
    vi.mocked(getEventCatalog).mockResolvedValue([
      {
        key: 'follow',
        display_name: '追隨',
        category_label: '追隨',
        accent: 'follow',
        requires_affiliate: true,
        capability_key: 'followers',
        default_template: '感謝 $(user) 的追隨！',
        default_enabled: true,
        variables: [],
        options_schema: [],
      },
    ])
  })

  it('owns EventSub response templates without loading Channel Points mappings', async () => {
    render(<Events />)

    expect(await screen.findByRole('heading', { name: 'Events' })).toBeInTheDocument()
    expect(screen.getByText('事件回覆')).toBeInTheDocument()
    expect(screen.getByText('感謝 $(user) 的追隨！')).toBeInTheDocument()
    await waitFor(() => expect(getEventConfigs).toHaveBeenCalledOnce())
    expect(getRedemptionConfigs).not.toHaveBeenCalled()
    expect(getTwitchRewards).not.toHaveBeenCalled()
    expect(screen.queryByText('頻道點數動作')).not.toBeInTheDocument()
  })

  it('renders the catalog-driven Watch Streak event', async () => {
    vi.mocked(getEventConfigs).mockResolvedValue([
      {
        id: 8,
        channel_id: 'channel-1',
        event_type: 'watch_streak',
        message_template: '感謝 $(@user) 的陪伴，已連續觀看 $(streak) 場直播！',
        enabled: false,
        options: {},
        trigger_count: null,
      },
    ])
    vi.mocked(getEventCatalog).mockResolvedValue([
      {
        key: 'watch_streak',
        display_name: '連續觀看',
        category_label: '觀看',
        accent: 'online',
        requires_affiliate: false,
        default_template: '感謝 $(@user) 的陪伴，已連續觀看 $(streak) 場直播！',
        default_enabled: false,
        variables: [
          { name: 'user', description: '分享者名稱', sample: '小明' },
          { name: '@user', description: '分享者名稱（含 @）', sample: '@小明' },
          { name: 'streak', description: '連續觀看場數', sample: '7' },
          { name: 'points', description: '獲得的忠誠點數', sample: '450' },
        ],
        options_schema: [],
      },
    ])

    render(<Events />)

    expect(await screen.findByText('連續觀看')).toBeInTheDocument()
    expect(screen.getByText('觀看')).toBeInTheDocument()
    expect(screen.getByText(/感謝 \$\(@user\) 的陪伴/)).toBeInTheDocument()
  })

  it('locks only the event whose optional Twitch scope is missing', async () => {
    capabilityMocks.isAvailable.mockImplementation(key => key !== 'followers')
    capabilityMocks.capability.mockImplementation(key =>
      key === 'followers'
        ? {
            key: 'followers',
            label: '追隨事件',
            credential: 'bot',
            available: false,
            missing_scopes: ['moderator:read:followers'],
            core: false,
          }
        : null
    )

    render(<Events />)

    expect(await screen.findByRole('switch', { name: '啟用 追隨' })).toBeDisabled()
    expect(screen.getByText('需要更新 Twitch 授權')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '更新 Twitch 授權' })).toBeInTheDocument()
  })
})
