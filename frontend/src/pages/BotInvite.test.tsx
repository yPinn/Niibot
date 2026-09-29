import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import { declineBotInvite, getPublicBotInvite } from '@/api/botAccounts'

import BotAuthorizationResult from './BotAuthorizationResult'
import BotInvite from './BotInvite'

vi.mock('@/api/botAccounts', () => ({
  declineBotInvite: vi.fn(),
  getPublicBotInvite: vi.fn(),
}))
vi.mock('@/hooks/useDocumentTitle')

const mockGetPublicBotInvite = getPublicBotInvite as MockedFunction<typeof getPublicBotInvite>
const mockDeclineBotInvite = declineBotInvite as MockedFunction<typeof declineBotInvite>

describe('Bot authorization public pages', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'alice',
      display_name: 'Alice',
      avatar: 'https://static-cdn.jtvnw.net/jtv_user_pictures/alice.png',
      purpose: 'link_new',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot', 'user:write:chat'],
      oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
    })
    mockDeclineBotInvite.mockResolvedValue({ status: 'declined' })
  })

  const renderInvite = (entry = '/bot-invite/opaque?nonce=state-nonce') =>
    render(
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/bot-invite/:publicToken" element={<BotInvite />} />
        </Routes>
      </MemoryRouter>
    )

  it('keeps the consent decision compact while preserving essential boundaries', async () => {
    renderInvite()

    expect(
      await screen.findByRole('heading', { name: '授權 Twitch 帳號擔任機器人' })
    ).toBeInTheDocument()
    expect(screen.getByText('邀請頻道')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Alice 的 Twitch 大頭貼' })).toBeInTheDocument()
    expect(screen.getAllByText('@alice').length).toBeGreaterThan(0)
    expect(screen.getByText(/想使用您的帳號，作為該頻道的機器人帳號/)).toBeInTheDocument()
    expect(screen.getByText('會做什麼')).toBeInTheDocument()
    expect(screen.getByText(/用這個帳號在 @alice 發言/)).toBeInTheDocument()
    expect(screen.getByText(/若它是頻道管理員，也能執行管理操作/)).toBeInTheDocument()
    expect(screen.getByText('可用頻道')).toBeInTheDocument()
    expect(screen.getByText(/只供 @alice 使用/)).toBeInTheDocument()
    expect(screen.getByText('撤回授權')).toBeInTheDocument()
    expect(screen.getByText(/不會取得你的 Twitch 密碼/)).toBeInTheDocument()
    expect(screen.getByText(/使用此帳號的頻道會停止相關功能/)).toBeInTheDocument()
    expect(screen.getByText('請使用專用的機器人帳號，不要使用頻道主帳號。')).toBeInTheDocument()
    expect(screen.getByText(/此連結只能使用一次/)).toBeInTheDocument()
    expect(document.body).not.toHaveTextContent(/\bBot\b|\bMOD\b|\bDashboard\b|scope/i)
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('marks the capability page as non-indexable and prevents referrer disclosure', async () => {
    const { unmount } = renderInvite()

    await screen.findByRole('heading', { name: '授權 Twitch 帳號擔任機器人' })
    expect(document.head.querySelector('meta[name="robots"]')).toHaveAttribute(
      'content',
      'noindex, nofollow'
    )
    expect(document.head.querySelector('meta[name="referrer"]')).toHaveAttribute(
      'content',
      'no-referrer'
    )

    unmount()
    expect(document.head.querySelector('meta[name="robots"]')).not.toBeInTheDocument()
    expect(document.head.querySelector('meta[name="referrer"]')).not.toBeInTheDocument()
  })

  it('restores pre-existing page metadata after leaving the capability page', async () => {
    const robots = document.createElement('meta')
    robots.name = 'robots'
    robots.content = 'index, follow'
    const referrer = document.createElement('meta')
    referrer.name = 'referrer'
    document.head.append(robots, referrer)

    const { unmount } = renderInvite()
    await screen.findByRole('heading', { name: '授權 Twitch 帳號擔任機器人' })
    expect(robots).toHaveAttribute('content', 'noindex, nofollow')
    expect(referrer).toHaveAttribute('content', 'no-referrer')

    unmount()
    expect(robots).toHaveAttribute('content', 'index, follow')
    expect(referrer).not.toHaveAttribute('content')
    robots.remove()
    referrer.remove()
  })

  it('leaves exact Twitch scopes to the provider consent page', async () => {
    renderInvite()

    await screen.findByRole('heading', { name: '授權 Twitch 帳號擔任機器人' })
    expect(screen.queryByText('user:bot')).not.toBeInTheDocument()
    expect(screen.queryByText('user:write:chat')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /完整 Twitch 權限清單/ })).not.toBeInTheDocument()
  })

  it('links to the trusted Twitch OAuth URL and supports declining', async () => {
    const user = userEvent.setup()
    renderInvite()

    expect(await screen.findByRole('link', { name: '前往 Twitch 授權' })).toHaveAttribute(
      'href',
      'https://id.twitch.tv/oauth2/authorize?safe=1'
    )

    await user.click(screen.getByRole('button', { name: '拒絕邀請' }))

    await waitFor(() => expect(mockDeclineBotInvite).toHaveBeenCalledWith('opaque', 'state-nonce'))
    expect(await screen.findByText('邀請已拒絕')).toBeInTheDocument()
  })

  it('adapts the intro copy to a reauthorize invite', async () => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'alice',
      display_name: 'Alice',
      avatar: null,
      purpose: 'reauthorize',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
    })
    renderInvite()

    expect(await screen.findByText(/邀請你重新授權這個 Twitch 帳號/)).toBeInTheDocument()
  })

  it('keeps the system-account reset flow separate from per-channel identity consent', async () => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'niibot_',
      display_name: '',
      avatar: null,
      purpose: 'system_default_reset',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
    })
    renderInvite()

    expect(await screen.findByText('系統機器人帳號')).toBeInTheDocument()
    expect(screen.getByText('@niibot_')).toBeInTheDocument()
    expect(screen.getByText('NI')).toBeInTheDocument()
    expect(screen.getByText('請重新授權這個 Twitch 帳號，讓 Niibot 繼續使用。')).toBeInTheDocument()
    expect(screen.getByText(/這次只會更新 Niibot 的系統機器人授權/)).toBeInTheDocument()
    expect(screen.getByText(/使用系統機器人的頻道會停止相關功能/)).toBeInTheDocument()
    expect(screen.queryByText('邀請頻道')).not.toBeInTheDocument()
    expect(screen.queryByText(/只限 @niibot_/)).not.toBeInTheDocument()
    expect(screen.queryByText(/請使用專用的機器人帳號/)).not.toBeInTheDocument()
  })

  it('rejects incomplete, unreadable, and untrusted invite links with safe copy', async () => {
    const { unmount } = renderInvite('/bot-invite/opaque')
    expect(await screen.findByText('這個授權連結不完整')).toBeInTheDocument()
    expect(mockGetPublicBotInvite).not.toHaveBeenCalled()
    unmount()

    mockGetPublicBotInvite.mockRejectedValueOnce(new Error('provider detail'))
    const unreadable = renderInvite()
    expect(
      await screen.findByText('無法讀取這個授權邀請，請向邀請人索取新連結')
    ).toBeInTheDocument()
    unreadable.unmount()

    mockGetPublicBotInvite.mockResolvedValueOnce({
      channel_name: 'alice',
      display_name: 'Alice',
      avatar: null,
      purpose: 'link_new',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: 'https://attacker.invalid/oauth',
    })
    renderInvite()
    expect(await screen.findByRole('button', { name: '授權連結無效' })).toBeDisabled()
    expect(screen.queryByRole('link', { name: '前往 Twitch 授權' })).not.toBeInTheDocument()
  })

  it.each([
    ['authorized', '授權已完成'],
    ['expired', '邀請已過期'],
  ] as const)('renders the terminal %s state without consent actions', async (status, message) => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'alice',
      display_name: 'Alice',
      avatar: null,
      purpose: 'link_new',
      status,
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: null,
    })
    renderInvite()

    expect(await screen.findByText(message)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '拒絕邀請' })).not.toBeInTheDocument()
  })

  it('keeps a decline failure on the consent page and offers a safe retry message', async () => {
    mockDeclineBotInvite.mockRejectedValueOnce(new Error('provider detail'))
    const user = userEvent.setup()
    renderInvite()

    await user.click(await screen.findByRole('button', { name: '拒絕邀請' }))

    expect(await screen.findByText('拒絕邀請失敗，請稍後再試')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '拒絕邀請' })).toBeEnabled()
  })

  it('renders a standalone success result without entering the dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/bot-auth/result?status=success']}>
        <BotAuthorizationResult />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: '授權已完成' })).toBeInTheDocument()
    expect(screen.getByText('邀請人現在可以在自己的頻道使用這個帳號。')).toBeInTheDocument()
    expect(screen.getByText('你可以關閉這個頁面。')).toBeInTheDocument()
    expect(screen.queryByText(/Dashboard/)).not.toBeInTheDocument()
  })

  it.each([
    ['authorization_denied', '你已取消 Twitch 授權。'],
    ['provider_unavailable', 'Twitch 授權暫時無法使用。'],
    ['bot_invite_wrong_account', '請使用邀請指定的 Twitch 帳號。'],
    ['bot_account_missing_scopes', '尚未完成必要授權。'],
    ['bot_account_role_conflict', '這個 Twitch 帳號目前無法作為機器人帳號。'],
  ])('shows only actionable bot authorization failure copy for %s', (reason, message) => {
    render(
      <MemoryRouter initialEntries={[`/bot-auth/result?status=error&reason=${reason}`]}>
        <BotAuthorizationResult />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: '授權未完成' })).toBeInTheDocument()
    expect(screen.getByText(message)).toBeInTheDocument()
  })

  it.each(['invalid_scope', 'missing_code', 'token_exchange_failed', 'secret-provider-value'])(
    'keeps internal bot authorization detail %s out of user-facing copy',
    reason => {
      render(
        <MemoryRouter initialEntries={[`/bot-auth/result?status=error&reason=${reason}`]}>
          <BotAuthorizationResult />
        </MemoryRouter>
      )

      expect(screen.getByText('授權未完成，請重新取得邀請連結。')).toBeInTheDocument()
      expect(screen.queryByText(reason)).not.toBeInTheDocument()
    }
  )
})
