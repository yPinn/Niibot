import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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
        requires_affiliate: false,
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
})
