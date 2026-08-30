import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/admin', () => ({
  approveActivationRequest: vi.fn(),
  createOwnerCode: vi.fn(),
  getActivationRequests: vi.fn(),
  getGrants: vi.fn(),
  getMembershipTimeline: vi.fn(),
  getOnboardingFunnel: vi.fn(),
  rejectActivationRequest: vi.fn(),
  revokeGrant: vi.fn(),
}))

import {
  getActivationRequests,
  getGrants,
  getMembershipTimeline,
  getOnboardingFunnel,
  type Grant,
} from '@/api/admin'

import { ActivationCard } from './ActivationCard'

const GRANT: Grant = {
  id: 1,
  kind: 'owner_manual',
  status: 'issued',
  platform_user_id: null,
  code_plain: 'NII-1234',
  reward_cost: null,
  channel_id: null,
  redemption_id: null,
  issued_at: '2026-08-29T02:00:00Z',
  expires_at: '2026-09-01T02:00:00Z',
  used_at: null,
  attempt_count: 0,
  display_name: 'Pilot',
  avatar: null,
  username: 'pilot',
}

const mockGetFunnel = getOnboardingFunnel as ReturnType<typeof vi.fn>
const mockGetRequests = getActivationRequests as ReturnType<typeof vi.fn>
const mockGetGrants = getGrants as ReturnType<typeof vi.fn>
const mockGetTimeline = getMembershipTimeline as ReturnType<typeof vi.fn>

describe('ActivationCard information architecture', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetFunnel.mockResolvedValue({
      active_members: 12,
      by_kind: [
        {
          kind: 'channel_points',
          issued_7d: 3,
          consumed_7d: 2,
          issued_30d: 10,
          consumed_30d: 4,
          issued_all: 30,
          consumed_all: 20,
          outstanding: 6,
        },
      ],
    })
    mockGetRequests.mockResolvedValue([])
    mockGetGrants.mockResolvedValue([GRANT])
    mockGetTimeline.mockResolvedValue([])
  })

  it('shows four plain-language authorization metrics', async () => {
    render(<ActivationCard />)

    expect(await screen.findByText('有效使用者')).toBeInTheDocument()
    expect(screen.getByText('近 30 日已發出')).toBeInTheDocument()
    expect(screen.getByText('近 30 日已啟用')).toBeInTheDocument()
    expect(screen.getByText('啟用率')).toBeInTheDocument()
    expect(screen.getByText('12')).toBeInTheDocument()
    expect(screen.getByText('10')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    expect(screen.getByText('40%')).toBeInTheDocument()
  })

  it('splits requests and activation codes into equal desktop workspaces', async () => {
    mockGetRequests.mockResolvedValue([
      {
        id: 'user-1',
        platform_user_id: 'channel-1',
        display_name: 'Applicant',
        username: 'applicant',
        avatar: null,
        note: '',
        created_at: '2026-08-29T02:00:00Z',
      },
    ])

    render(<ActivationCard />)

    const workspace = await screen.findByRole('group', { name: '授權作業' })
    expect(workspace).toHaveClass('xl:grid-cols-2')
    expect(workspace).toHaveTextContent('授權申請')
    expect(workspace).toHaveTextContent('啟用碼')
    expect(screen.getByRole('article', { name: 'Pilot 的啟用碼' })).toBeInTheDocument()
  })

  it('distinguishes a grants fetch failure from an empty result and retries it', async () => {
    const user = userEvent.setup()
    mockGetGrants.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([GRANT])

    render(<ActivationCard />)

    expect(await screen.findByText('啟用碼載入失敗')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重試啟用碼' }))

    expect(await screen.findByText('NII-1234')).toBeInTheDocument()
    expect(mockGetGrants).toHaveBeenCalledTimes(2)
  })

  it('presents timeline event, actor, time and reason as separate information', async () => {
    const user = userEvent.setup()
    mockGetRequests.mockResolvedValue([
      {
        id: 'user-1',
        platform_user_id: 'channel-1',
        display_name: 'Pilot',
        username: 'pilot',
        avatar: null,
        note: '',
        created_at: '2026-08-29T02:00:00Z',
      },
    ])
    mockGetTimeline.mockResolvedValue([
      {
        id: 7,
        event_type: 'suspended',
        actor_type: 'owner',
        actor_user_id: 'owner-1',
        reason: '帳號安全風險',
        metadata: {},
        occurred_at: '2026-08-30T02:00:00Z',
      },
    ])

    render(<ActivationCard />)
    await user.click(await screen.findByRole('button', { name: /^Pilot/ }))

    expect(await screen.findByText('停權')).toBeInTheDocument()
    expect(screen.getByText('管理員')).toBeInTheDocument()
    expect(screen.getByText('原因')).toBeInTheDocument()
    expect(screen.getByText('帳號安全風險')).toBeInTheDocument()
  })
})
