import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/admin', () => ({
  createOwnerCode: vi.fn(),
  getGrants: vi.fn(),
  getOnboardingFunnel: vi.fn(),
  revokeGrant: vi.fn(),
}))

import { getGrants, getOnboardingFunnel, type Grant } from '@/api/admin'

import { ActivationCodes } from './ActivationCodes'

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
const mockGetGrants = getGrants as ReturnType<typeof vi.fn>

describe('ActivationCodes', () => {
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
    mockGetGrants.mockResolvedValue([GRANT])
  })

  it('summarizes the 30-day channel-point funnel in one line', async () => {
    render(<ActivationCodes />)

    expect(await screen.findByText('近 30 日 發出 10 · 啟用 4（40%）')).toBeInTheDocument()
  })

  it('lists only unused codes with a revoke action', async () => {
    render(<ActivationCodes />)

    const row = await screen.findByRole('listitem', { name: 'Pilot 的啟用碼' })
    expect(row).toHaveTextContent('NII-1234')
    expect(mockGetGrants).toHaveBeenCalledWith({ status: 'issued' })
    expect(screen.getByRole('button', { name: '撤銷 Pilot 的啟用碼' })).toBeInTheDocument()
  })

  it('says so when no code is waiting to be used', async () => {
    mockGetGrants.mockResolvedValue([])
    render(<ActivationCodes />)

    expect(await screen.findByText('沒有待使用的啟用碼')).toBeInTheDocument()
  })

  it('distinguishes a grants fetch failure from an empty result and retries it', async () => {
    const user = userEvent.setup()
    mockGetGrants.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([GRANT])

    render(<ActivationCodes />)

    expect(await screen.findByText('載入失敗')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重試' }))

    expect(await screen.findByText('NII-1234')).toBeInTheDocument()
    expect(mockGetGrants).toHaveBeenCalledTimes(2)
  })
})
