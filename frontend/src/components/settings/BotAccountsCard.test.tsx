import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import {
  checkBotAuthorization,
  checkBroadcasterAuthorization,
  createBotInvite,
  createBotReauthorizationInvite,
  disconnectBroadcasterAuthorization,
  getBotAccountSelection,
  getBotInviteStatus,
  getBroadcasterAuthorization,
  listBotAccounts,
  unlinkBotAccount,
  updateBotAccountSelection,
} from '@/api/botAccounts'
import { openTwitchOAuth } from '@/api/twitchOAuth'
import { useTenant } from '@/contexts/TenantContext'

import { BotAccountsCard } from './BotAccountsCard'

vi.mock('@/api/botAccounts', () => ({
  checkBotAuthorization: vi.fn(),
  checkBroadcasterAuthorization: vi.fn(),
  createBotInvite: vi.fn(),
  createBotReauthorizationInvite: vi.fn(),
  disconnectBroadcasterAuthorization: vi.fn(),
  getBotAccountSelection: vi.fn(),
  getBroadcasterAuthorization: vi.fn(),
  getBotInviteStatus: vi.fn(),
  listBotAccounts: vi.fn(),
  updateBotAccountSelection: vi.fn(),
  unlinkBotAccount: vi.fn(),
}))
vi.mock('@/contexts/TenantContext')
vi.mock('@/api/twitchOAuth', () => ({
  openTwitchOAuth: vi.fn(),
}))

const mockUseTenant = useTenant as MockedFunction<typeof useTenant>
const mockListBotAccounts = listBotAccounts as MockedFunction<typeof listBotAccounts>
const mockCreateBotInvite = createBotInvite as MockedFunction<typeof createBotInvite>
const mockCreateBotReauthorizationInvite = createBotReauthorizationInvite as MockedFunction<
  typeof createBotReauthorizationInvite
>
const mockGetBotInviteStatus = getBotInviteStatus as MockedFunction<typeof getBotInviteStatus>
const mockGetBotAccountSelection = getBotAccountSelection as MockedFunction<
  typeof getBotAccountSelection
>
const mockGetBroadcasterAuthorization = getBroadcasterAuthorization as MockedFunction<
  typeof getBroadcasterAuthorization
>
const mockCheckBotAuthorization = checkBotAuthorization as MockedFunction<
  typeof checkBotAuthorization
>
const mockCheckBroadcasterAuthorization = checkBroadcasterAuthorization as MockedFunction<
  typeof checkBroadcasterAuthorization
>
const mockUnlinkBotAccount = unlinkBotAccount as MockedFunction<typeof unlinkBotAccount>
const mockDisconnectBroadcasterAuthorization = disconnectBroadcasterAuthorization as MockedFunction<
  typeof disconnectBroadcasterAuthorization
>
const mockUpdateBotAccountSelection = updateBotAccountSelection as MockedFunction<
  typeof updateBotAccountSelection
>
const mockOpenTwitchOAuth = openTwitchOAuth as MockedFunction<typeof openTwitchOAuth>

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
        authorization_status: 'valid',
        last_checked_at: '2026-09-20T01:00:00Z',
        linked_at: null,
        is_active: true,
        is_desired: true,
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
        authorization_status: 'temporarily_unavailable',
        last_checked_at: '2026-09-20T00:30:00Z',
        linked_at: '2026-09-01T01:00:00Z',
        is_active: false,
        is_desired: false,
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
    mockGetBotAccountSelection.mockResolvedValue({
      desired_bot_user_id: null,
      active_bot_user_id: null,
      selection_version: 0,
      acked_version: 0,
      status: 'active',
      error_code: null,
    })
    mockUpdateBotAccountSelection.mockResolvedValue({
      desired_bot_user_id: 'bot-b',
      active_bot_user_id: null,
      selection_version: 1,
      acked_version: 0,
      status: 'switching',
      error_code: null,
    })
    mockGetBroadcasterAuthorization.mockResolvedValue({
      channel_id: 'channel-a',
      channel_name: 'alice',
      display_name: 'Alice',
      enabled: true,
      status: 'valid',
      last_checked_at: '2026-09-20T01:00:00Z',
      last_validated_at: '2026-09-20T01:00:00Z',
      error_code: null,
    })
    mockCheckBotAuthorization.mockResolvedValue({
      status: 'valid',
      last_checked_at: '2026-09-20T01:10:00Z',
      last_validated_at: '2026-09-20T01:10:00Z',
      error_code: null,
    })
    mockCheckBroadcasterAuthorization.mockResolvedValue({
      status: 'valid',
      last_checked_at: '2026-09-20T01:10:00Z',
      last_validated_at: '2026-09-20T01:10:00Z',
      error_code: null,
    })
    mockUnlinkBotAccount.mockResolvedValue({
      credential_retained: false,
      upstream_revoke_confirmed: true,
    })
    mockDisconnectBroadcasterAuthorization.mockResolvedValue({
      credential_retained: false,
      upstream_revoke_confirmed: true,
    })
    mockOpenTwitchOAuth.mockResolvedValue(undefined)
  })

  it('lists only server-returned accounts and creates a shareable owner invite', async () => {
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByText('Twitch 帳號與授權')).toBeInTheDocument()
    expect(screen.getByText('實況主帳號')).toBeInTheDocument()
    expect((await screen.findAllByText('Niibot')).length).toBeGreaterThan(0)
    expect(screen.getByText('Bot B')).toBeInTheDocument()
    expect(screen.getByText('系統管理')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '邀請帳號' }))

    await waitFor(() => expect(mockCreateBotInvite).toHaveBeenCalledWith('channel-a'))
    expect(screen.getByDisplayValue(/\/bot-invite\/opaque/)).toBeInTheDocument()
    expect(screen.queryByText(/access_token|refresh_token/)).not.toBeInTheDocument()
    const copyInvite = screen.getByRole('button', { name: '複製邀請連結' })
    expect(copyInvite).not.toHaveTextContent('複製')
    expect(screen.getByRole('link', { name: '開啟邀請連結' })).not.toHaveTextContent('開啟')
    await user.hover(copyInvite)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('複製連結')

    await user.click(screen.getByRole('button', { name: '重新授權 Bot B' }))
    expect(mockCreateBotReauthorizationInvite).toHaveBeenCalledWith('channel-a', 'bot-b')
  })

  it('keeps copy concise and exposes repeated actions as labeled icon buttons', async () => {
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByText('檢查 Twitch 授權，並選擇聊天室發言帳號。')).toBeInTheDocument()
    expect(screen.getByText('解除後，Niibot 會停止這個頻道的服務。')).toBeInTheDocument()
    expect(
      screen.getByText(
        /同一個 Bot 的憑證只保存一份；每個頻道仍需帳號本人同意。.*邀請連結只能使用一次，30 分鐘後失效。/
      )
    ).toBeInTheDocument()

    const checkBroadcaster = await screen.findByRole('button', { name: '重新檢查實況主授權' })
    const reauthorizeBroadcaster = screen.getByRole('button', {
      name: '重新授權實況主帳號',
    })
    const checkBot = screen.getByRole('button', { name: '重新檢查 Bot B' })
    const reauthorizeBot = screen.getByRole('button', { name: '重新授權 Bot B' })

    expect(checkBroadcaster).not.toHaveTextContent('重新檢查')
    expect(reauthorizeBroadcaster).not.toHaveTextContent('重新授權')
    expect(checkBot).not.toHaveTextContent('重新檢查')
    expect(reauthorizeBot).not.toHaveTextContent('重新授權')
    expect(screen.getByRole('button', { name: '解除授權' })).toHaveTextContent('解除授權')

    await user.hover(checkBroadcaster)
    expect(await screen.findByRole('tooltip')).toHaveTextContent('重新檢查')
  })

  it('switches a healthy approved account and reports the pending sender clearly', async () => {
    mockListBotAccounts.mockResolvedValueOnce([
      {
        platform_user_id: 'niibot',
        login: 'niibot_',
        display_name: 'Niibot',
        avatar: null,
        is_system_default: true,
        requires_reauth: false,
        last_validated_at: null,
        revoked_at: null,
        authorization_status: 'valid',
        last_checked_at: null,
        linked_at: null,
        is_active: true,
        is_desired: true,
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
        authorization_status: 'valid',
        last_checked_at: null,
        linked_at: null,
        is_active: false,
        is_desired: false,
      },
    ])
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByRole('status')).toHaveTextContent('目前使用：Niibot')
    await user.click(screen.getByRole('combobox', { name: '聊天室發言帳號' }))
    await user.click(screen.getByRole('option', { name: /Bot B/ }))
    await user.click(screen.getByRole('button', { name: '套用發言帳號' }))

    await waitFor(() =>
      expect(mockUpdateBotAccountSelection).toHaveBeenCalledWith('channel-a', 'bot-b')
    )
    expect(screen.getByRole('status')).toHaveTextContent('正在切換至 Bot B')
    expect(screen.getByRole('status')).toHaveTextContent('完成前仍使用 Niibot')
  })

  it('disables using the broadcaster identity as its own bot', async () => {
    mockListBotAccounts.mockResolvedValueOnce([
      {
        platform_user_id: 'niibot',
        login: 'niibot_',
        display_name: 'Niibot',
        avatar: null,
        is_system_default: true,
        requires_reauth: false,
        last_validated_at: null,
        revoked_at: null,
        authorization_status: 'valid',
        last_checked_at: null,
        linked_at: null,
        is_active: true,
        is_desired: true,
      },
      {
        platform_user_id: 'channel-a',
        login: 'alice',
        display_name: 'Alice',
        avatar: null,
        is_system_default: false,
        requires_reauth: false,
        last_validated_at: null,
        revoked_at: null,
        authorization_status: 'valid',
        last_checked_at: null,
        linked_at: '2026-09-01T01:00:00Z',
        is_active: false,
        is_desired: false,
      },
    ])
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    await user.click(await screen.findByRole('combobox', { name: '聊天室發言帳號' }))
    const sameIdentity = screen.getByRole('option', { name: 'Alice（不能使用頻道主帳號）' })

    expect(sameIdentity).toHaveAttribute('aria-disabled', 'true')
  })

  it('turns runtime selection failures into safe, actionable copy', async () => {
    mockGetBotAccountSelection.mockResolvedValueOnce({
      desired_bot_user_id: 'bot-b',
      active_bot_user_id: null,
      selection_version: 3,
      acked_version: 2,
      status: 'failed',
      error_code: 'bot_not_moderator',
    })

    render(<BotAccountsCard />)

    const status = await screen.findByRole('status')
    expect(status).toHaveTextContent('仍使用 Niibot')
    expect(status).toHaveTextContent('請先在 Twitch 將 Bot B 設為 MOD')
    expect(status).not.toHaveTextContent('bot_not_moderator')
  })

  it.each([
    ['bot_authorization_required', '請由頻道擁有者重新授權 Bot B，再重試。'],
    ['bot_scope_required', '請由頻道擁有者重新授權 Bot B，再重試。'],
    ['broadcaster_authorization_required', '請由頻道擁有者更新實況主授權，再重試。'],
    ['broadcaster_scope_required', '請由頻道擁有者更新實況主授權，再重試。'],
    ['provider_unavailable', '請稍後再試；若持續失敗，請檢查 Twitch 授權與 MOD 設定。'],
  ])('maps %s to safe recovery guidance', async (errorCode, expectedCopy) => {
    mockGetBotAccountSelection.mockResolvedValueOnce({
      desired_bot_user_id: 'bot-b',
      active_bot_user_id: null,
      selection_version: 3,
      acked_version: 2,
      status: 'failed',
      error_code: errorCode,
    })

    render(<BotAccountsCard />)

    expect(await screen.findByRole('status')).toHaveTextContent(expectedCopy)
    expect(screen.queryByText(errorCode)).not.toBeInTheDocument()
  })

  it('finishes an immediately acknowledged switch and refreshes account state', async () => {
    mockListBotAccounts.mockResolvedValue(
      (await mockListBotAccounts()).map(account => ({
        ...account,
        authorization_status: 'valid',
      }))
    )
    mockListBotAccounts.mockClear()
    mockUpdateBotAccountSelection.mockResolvedValueOnce({
      desired_bot_user_id: 'bot-b',
      active_bot_user_id: 'bot-b',
      selection_version: 1,
      acked_version: 1,
      status: 'active',
      error_code: null,
    })
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    await user.click(await screen.findByRole('combobox', { name: '聊天室發言帳號' }))
    await user.click(screen.getByRole('option', { name: /Bot B/ }))
    await user.click(screen.getByRole('button', { name: '套用發言帳號' }))

    await waitFor(() => expect(mockListBotAccounts).toHaveBeenCalledTimes(2))
    expect(screen.getByRole('status')).toHaveTextContent('目前使用：Bot B')
  })

  it('shows unknown check times without leaking invalid timestamps', async () => {
    mockGetBroadcasterAuthorization.mockResolvedValueOnce({
      channel_id: 'channel-a',
      channel_name: 'alice',
      display_name: '',
      enabled: false,
      status: 'not_checked',
      last_checked_at: 'not-a-date',
      last_validated_at: null,
      error_code: null,
    })

    render(<BotAccountsCard />)

    expect(await screen.findByText('檢查時間未知')).toBeInTheDocument()
    expect(screen.getByText('Niibot 已停止')).toBeInTheDocument()
    expect(screen.getByText('@alice')).toBeInTheDocument()
  })

  it('retries selection state independently when its initial request fails', async () => {
    mockGetBotAccountSelection.mockRejectedValueOnce(new Error('selection unavailable'))
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByRole('alert')).toHaveTextContent('發言帳號選擇載入失敗')
    await user.click(screen.getByRole('button', { name: '重新載入發言帳號選擇' }))

    expect(await screen.findByRole('status')).toHaveTextContent('目前使用：Niibot')
    expect(mockGetBotAccountSelection).toHaveBeenCalledTimes(2)
    expect(mockListBotAccounts).toHaveBeenCalledTimes(1)
  })

  it('uses plain-language health states and guards tenant bot removal', async () => {
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    expect(await screen.findByText('暫時無法確認')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新檢查 Bot B' }))
    await waitFor(() =>
      expect(mockCheckBotAuthorization).toHaveBeenCalledWith('channel-a', 'bot-b')
    )

    await user.click(screen.getByRole('button', { name: '從這個頻道移除 Bot B' }))
    expect(screen.getByRole('alertdialog')).toHaveTextContent('其他頻道若仍在使用，授權會保留')
    expect(screen.getByRole('alertdialog')).toHaveTextContent('既有設定與歷史紀錄不會刪除')
    await user.click(screen.getByRole('button', { name: '確認移除' }))

    await waitFor(() => expect(mockUnlinkBotAccount).toHaveBeenCalledWith('channel-a', 'bot-b'))
  })

  it('explains broadcaster disconnect impact and requires typing the channel login', async () => {
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    await screen.findByText('@alice')
    await user.click(screen.getByRole('button', { name: '解除授權' }))

    const confirm = screen.getByRole('button', { name: '確認停止並解除' })
    expect(confirm).toBeDisabled()
    expect(screen.getByRole('alertdialog')).toHaveTextContent('你目前所有 Dashboard 登入會立即登出')
    expect(screen.getByRole('alertdialog')).toHaveTextContent('設定與歷史紀錄會保留')
    await user.type(screen.getByLabelText('輸入頻道帳號以確認'), 'alice')
    expect(confirm).toBeEnabled()
  })

  it('guards broadcaster reauthorization while OAuth startup is pending and recovers on failure', async () => {
    let rejectOAuth!: (reason?: unknown) => void
    mockOpenTwitchOAuth.mockImplementation(
      () =>
        new Promise<void>((_resolve, reject) => {
          rejectOAuth = reject
        })
    )
    const user = userEvent.setup()
    render(<BotAccountsCard />)

    const reauthorize = await screen.findByRole('button', { name: '重新授權實況主帳號' })
    await user.click(reauthorize)

    expect(reauthorize).toBeDisabled()
    rejectOAuth(new Error('popup blocked'))
    await waitFor(() => expect(reauthorize).toBeEnabled())
  })

  it('lets a MOD switch approved accounts but not manage credentials', async () => {
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

    expect((await screen.findAllByText('Niibot')).length).toBeGreaterThan(0)
    expect(screen.getByRole('combobox', { name: '聊天室發言帳號' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '邀請帳號' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '重新授權 Bot B' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '從這個頻道移除 Bot B' })).not.toBeInTheDocument()
  })

  it('keeps broadcaster data visible when the bot account request fails and retries it alone', async () => {
    mockListBotAccounts.mockRejectedValueOnce(new Error('accounts unavailable'))
    const user = userEvent.setup()

    render(<BotAccountsCard />)

    expect(await screen.findByText('@alice')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('發言帳號載入失敗')
    expect(screen.queryByText('Bot B')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重新載入聊天室發言帳號' }))

    expect(await screen.findByText('Bot B')).toBeInTheDocument()
    expect(mockGetBroadcasterAuthorization).toHaveBeenCalledTimes(1)
    expect(mockListBotAccounts).toHaveBeenCalledTimes(2)
  })

  it('keeps bot account data visible when the broadcaster request fails and retries it alone', async () => {
    mockGetBroadcasterAuthorization.mockRejectedValueOnce(new Error('broadcaster unavailable'))
    const user = userEvent.setup()

    render(<BotAccountsCard />)

    expect(await screen.findByText('Bot B')).toBeInTheDocument()
    expect(await screen.findByRole('alert')).toHaveTextContent('實況主授權載入失敗')
    expect(screen.queryByText('@alice')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '重新載入實況主授權' }))

    expect(await screen.findByText('@alice')).toBeInTheDocument()
    expect(mockGetBroadcasterAuthorization).toHaveBeenCalledTimes(2)
    expect(mockListBotAccounts).toHaveBeenCalledTimes(1)
  })
})
