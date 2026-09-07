import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import { deletePaymentConfig, getPaymentConfigs, upsertPaymentConfig } from '@/api/donation'
import { useAuth } from '@/contexts/AuthContext'
import { useTenant } from '@/contexts/TenantContext'

import { PaymentConfigCard } from './PaymentConfigCard'

vi.mock('@/api/donation', () => ({
  getPaymentConfigs: vi.fn(),
  upsertPaymentConfig: vi.fn(),
  deletePaymentConfig: vi.fn(),
  NEEDS_HASH: { ecpay: true, opay: true, paypal: false, newebpay: true },
  PLATFORM_LABELS: {
    ecpay: '綠界 ECPay',
    opay: '歐付寶 OPay',
    paypal: 'PayPal',
    newebpay: '藍新金流 NewebPay',
  },
}))
vi.mock('@/contexts/AuthContext')
vi.mock('@/contexts/TenantContext')

const mockUseAuth = useAuth as MockedFunction<typeof useAuth>
const mockUseTenant = useTenant as MockedFunction<typeof useTenant>
const mockGet = getPaymentConfigs as MockedFunction<typeof getPaymentConfigs>
const mockUpsert = upsertPaymentConfig as MockedFunction<typeof upsertPaymentConfig>
const mockDelete = deletePaymentConfig as MockedFunction<typeof deletePaymentConfig>

function tenant(capabilities: string[]) {
  return {
    tenants: [],
    activeTenant: capabilities.length
      ? ({ channel_id: 'c1', capabilities } as never)
      : ({ channel_id: 'c1', capabilities: [] } as never),
    isInitialized: true,
    isLoading: false,
    error: null,
    refreshTenants: vi.fn(),
    selectTenant: vi.fn(),
  } as never
}

beforeEach(() => {
  vi.clearAllMocks()
  mockUseAuth.mockReturnValue({
    user: { name: 'alice', platform: 'twitch', broadcaster_type: 'affiliate' },
    isAffiliate: true,
  } as never)
  mockUseTenant.mockReturnValue(tenant(['manage_billing']))
  mockGet.mockResolvedValue([])
  mockUpsert.mockResolvedValue({} as never)
  mockDelete.mockResolvedValue()
})

describe('PaymentConfigCard', () => {
  it('renders nothing without the manage_billing capability', () => {
    mockUseTenant.mockReturnValue(tenant([]))
    const { container } = render(<PaymentConfigCard />)
    expect(container).toBeEmptyDOMElement()
    expect(mockGet).not.toHaveBeenCalled()
  })

  it('marks platforms that already have a stored config', async () => {
    mockGet.mockResolvedValue([
      {
        platform: 'ecpay',
        merchant_id: '2000132',
        has_hash: true,
        min_amount: 50,
        media_share_enabled: false,
        enabled: true,
        updated_at: null,
      },
    ])
    render(<PaymentConfigCard />)
    expect(await screen.findByText('已設定')).toBeInTheDocument()
  })

  const existingEcpay = {
    platform: 'ecpay' as const,
    merchant_id: '2000132',
    has_hash: true,
    min_amount: 50,
    media_share_enabled: false,
    enabled: true,
    updated_at: null,
  }

  it('persists the enable toggle immediately and reverts on failure', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue([existingEcpay])
    mockUpsert.mockRejectedValueOnce(new Error('boom'))
    render(<PaymentConfigCard />)

    const toggle = await screen.findByRole('switch', { name: '啟用' })
    expect(toggle).toBeChecked()

    await user.click(toggle)
    await waitFor(() =>
      expect(mockUpsert).toHaveBeenCalledWith('ecpay', expect.objectContaining({ enabled: false }))
    )
    // API rejected → optimistic flip is rolled back
    await waitFor(() => expect(screen.getByRole('switch', { name: '啟用' })).toBeChecked())
  })

  it('does not show an enable toggle before the platform is saved', async () => {
    render(<PaymentConfigCard />)
    await screen.findByText('綠界 ECPay')
    expect(screen.queryByRole('switch', { name: '啟用' })).not.toBeInTheDocument()
  })

  async function openEcpay(user: ReturnType<typeof userEvent.setup>) {
    const card = (await screen.findByText('綠界 ECPay')).closest('[data-slot="card"]')!
    await user.click(within(card).getByText('綠界 ECPay'))
    return card as HTMLElement
  }

  it('keeps save disabled until a merchant id is entered', async () => {
    const user = userEvent.setup()
    render(<PaymentConfigCard />)
    const card = await openEcpay(user)

    expect(within(card).getByRole('button', { name: '儲存' })).toBeDisabled()
    await user.type(within(card).getByLabelText('商店代號'), '2000132')
    expect(within(card).getByRole('button', { name: '儲存' })).toBeEnabled()
  })

  it('clamps min amount to the backend bounds on save', async () => {
    const user = userEvent.setup()
    render(<PaymentConfigCard />)
    const card = await openEcpay(user)
    await user.type(within(card).getByLabelText('商店代號'), '2000132')

    const amount = within(card).getByRole('spinbutton')
    await user.clear(amount)
    await user.type(amount, '0')
    await user.click(within(card).getByRole('button', { name: '儲存' }))
    await waitFor(() =>
      expect(mockUpsert).toHaveBeenCalledWith('ecpay', expect.objectContaining({ min_amount: 30 }))
    )

    mockUpsert.mockClear()
    await user.clear(amount)
    await user.type(amount, '999999')
    await user.click(within(card).getByRole('button', { name: '儲存' }))
    await waitFor(() =>
      expect(mockUpsert).toHaveBeenCalledWith(
        'ecpay',
        expect.objectContaining({ min_amount: 99999 })
      )
    )
  })

  it('deletes a config after confirmation', async () => {
    const user = userEvent.setup()
    mockGet.mockResolvedValue([
      {
        platform: 'ecpay',
        merchant_id: '2000132',
        has_hash: true,
        min_amount: 50,
        media_share_enabled: false,
        enabled: true,
        updated_at: null,
      },
    ])
    render(<PaymentConfigCard />)

    await user.click(await screen.findByRole('button', { name: '刪除 綠界 ECPay 設定' }))
    await user.click(await screen.findByRole('button', { name: /刪除|確定/ }))

    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith('ecpay'))
  })
})
