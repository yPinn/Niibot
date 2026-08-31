import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import {
  createBotInvite,
  createBotReauthorizationInvite,
  getBotInviteStatus,
  listBotAccounts,
} from '@/api/botAccounts'
import { useTenant } from '@/contexts/TenantContext'

import { BotAccountsCard } from './BotAccountsCard'

vi.mock('@/api/botAccounts', () => ({
  createBotInvite: vi.fn(),
  createBotReauthorizationInvite: vi.fn(),
  getBotInviteStatus: vi.fn(),
  listBotAccounts: vi.fn(),
}))
vi.mock('@/contexts/TenantContext')

const mockUseTenant = useTenant as MockedFunction<typeof useTenant>
const mockListBotAccounts = listBotAccounts as MockedFunction<typeof listBotAccounts>
const mockCreateBotInvite = createBotInvite as MockedFunction<typeof createBotInvite>
const mockCreateBotReauthorizationInvite = createBotReauthorizationInvite as MockedFunction<
  typeof createBotReauthorizationInvite
>
const mockGetBotInviteStatus = getBotInviteStatus as MockedFunction<typeof getBotInviteStatus>

const ownerTenant = {
  channel_id: 'channel-a',
  channel_name: 'alice',
  display_name: 'Alice',
  enabled: true,
  role: 'owner' as const,
  capabilities: [
    'edit_operations',
    'switch_bot',
    'toggle_bot',
    'manage_bot_accounts',
    'manage_members',
    'manage_billing',
    'manage_security',
  ] as const,
}

describe('BotAccountsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseTenant.mockReturnValue({
      tenants: [ownerTenant],
      activeTenant: ownerTenant,
      isInitialized: true,
      isLoading: false,
      error: null,
      refreshTenants: vi.fn(),
      selectTenant: vi.fn(),
    })
    mockListBotAccounts.mockResolvedValue([
      {
        platform_user_id: 'niibot',
        login: 'niibot_',
        display_name: 'Niibot',
        avatar: null,
        is_system_default: true,
        requires_reauth: false,
        last_validated_at: null,
        revoked_at: null,
      },
      {
        platform_user_id: 'bot-b',
        login: 'bot_b',
        display_name: 'Bot B',
        avatar: null,
        is_system_default: false,
        requires_reauth: false,
        last_validated_at: null,
        revoked_at: null,
      },
    ])
    mockCreateBotInvite.mockResolvedValue({
      invite_id: 'invite-1',
      public_url: 'https://niibot.test/bot-invite/opaque?nonce=state-nonce',
      expires_at: '2026-08-31T12:00:00Z',
    })
    mockCreateBotReauthorizationInvite.mockResolvedValue({
      invite_id: 'invite-2',
      public_url: 'https://niibot.test/bot-invite/reset?nonce=state-nonce',
      expires_at: '2026-08-31T12:00:00Z',
    })
    mockGetBotInviteStatus.mockResolvedValue({
      invite_id: 'invite-1',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      consumed_at: null,
      account: null,
    })
  })

  it('lists only server-returned accounts and creates a shareable owner invite', async () => {
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByText('Niibot')).toBeInTheDocument()
    expect(screen.getByText('Bot B')).toBeInTheDocument()
    expect(screen.getByText('系統預設')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '邀請 Bot 帳號' }))

    await waitFor(() => expect(mockCreateBotInvite).toHaveBeenCalledWith('channel-a'))
    expect(screen.getByDisplayValue(/\/bot-invite\/opaque/)).toBeInTheDocument()
    expect(screen.queryByText(/access_token|refresh_token/)).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重新授權 Bot B' }))
    expect(mockCreateBotReauthorizationInvite).toHaveBeenCalledWith('channel-a', 'bot-b')
  })

  it('lets a MOD inspect approved accounts but not create credential invitations', async () => {
    mockUseTenant.mockReturnValue({
      tenants: [
        {
          ...ownerTenant,
          role: 'manager',
          capabilities: ['edit_operations', 'switch_bot', 'toggle_bot'],
        },
      ],
      activeTenant: {
        ...ownerTenant,
        role: 'manager',
        capabilities: ['edit_operations', 'switch_bot', 'toggle_bot'],
      },
      isInitialized: true,
      isLoading: false,
      error: null,
      refreshTenants: vi.fn(),
      selectTenant: vi.fn(),
    })

    render(<BotAccountsCard />)

    expect(await screen.findByText('Niibot')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '邀請 Bot 帳號' })).not.toBeInTheDocument()
  })
})
