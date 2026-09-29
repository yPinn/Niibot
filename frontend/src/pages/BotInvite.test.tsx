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

  it('explains the invite in plain language and discloses the boundaries', async () => {
    renderInvite()

    expect(await screen.findByRole('heading', { name: '授權 Bot 帳號' })).toBeInTheDocument()
    // who invited you + which channel your account acts in
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getAllByText('@alice').length).toBeGreaterThan(0)
    expect(screen.getByText(/邀請你讓 Niibot 以你的 Twitch 帳號/)).toBeInTheDocument()
    // plain-language capability summary, not raw scope codes
    expect(screen.getByText(/發送機器人回覆與指令/)).toBeInTheDocument()
    // disclosures Twitch's own consent screen cannot make
    expect(screen.getByText(/不會建立 Niibot 帳號/)).toBeInTheDocument()
    expect(screen.getByText(/拿不到你的 Twitch 密碼/)).toBeInTheDocument()
    expect(screen.getByText(/其他頻道必須另行取得你的同意/)).toBeInTheDocument()
    expect(screen.getByText(/也用來登入自己的 Niibot 頻道/)).toBeInTheDocument()
    expect(screen.getByText(/會停止 Niibot 對這個 Twitch 帳號的全部授權/)).toBeInTheDocument()
    expect(screen.getByText(/只能使用一次/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
  })

  it('marks the capability page as non-indexable and prevents referrer disclosure', async () => {
    const { unmount } = renderInvite()

    await screen.findByRole('heading', { name: '授權 Bot 帳號' })
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
    await screen.findByRole('heading', { name: '授權 Bot 帳號' })
    expect(robots).toHaveAttribute('content', 'noindex, nofollow')
    expect(referrer).toHaveAttribute('content', 'no-referrer')

    unmount()
    expect(robots).toHaveAttribute('content', 'index, follow')
    expect(referrer).not.toHaveAttribute('content')
    robots.remove()
    referrer.remove()
  })

  it('keeps the raw Twitch scope list collapsed by default to avoid duplicating the OAuth screen', async () => {
    const user = userEvent.setup()
    renderInvite()

    await screen.findByRole('heading', { name: '授權 Bot 帳號' })
    expect(screen.queryByText('user:bot')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /完整 Twitch 權限清單（2 項）/ }))

    expect(await screen.findByText('user:bot')).toBeInTheDocument()
    expect(screen.getByText('user:write:chat')).toBeInTheDocument()
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
    expect(await screen.findByText('已拒絕這次 Bot 授權邀請')).toBeInTheDocument()
  })

  it('adapts the intro copy to a reauthorize invite', async () => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'alice',
      display_name: 'Alice',
      purpose: 'reauthorize',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
    })
    renderInvite()

    expect(await screen.findByText(/請你重新授權這個 Bot 帳號/)).toBeInTheDocument()
  })

  it('keeps the system-account reset flow separate from per-channel identity consent', async () => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'niibot_',
      display_name: '',
      purpose: 'system_default_reset',
      status: 'pending',
      expires_at: '2026-08-31T12:00:00Z',
      required_scopes: ['user:bot'],
      oauth_url: 'https://id.twitch.tv/oauth2/authorize?safe=1',
    })
    renderInvite()

    expect(await screen.findByText('請你重新授權 Niibot 的系統預設 Bot 帳號。')).toBeInTheDocument()
    expect(screen.queryByText(/觀眾看到的發言者/)).not.toBeInTheDocument()
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
    ['authorized', '這次 Bot 授權已經完成'],
    ['expired', '這個 Bot 授權邀請已過期'],
  ] as const)('renders the terminal %s state without consent actions', async (status, message) => {
    mockGetPublicBotInvite.mockResolvedValue({
      channel_name: 'alice',
      display_name: 'Alice',
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

    expect(screen.getByRole('heading', { name: 'Bot 授權完成' })).toBeInTheDocument()
    expect(screen.getByText('邀請人現在可以在自己的頻道選用這個 Bot 帳號。')).toBeInTheDocument()
    expect(screen.getByText('你可以關閉這個頁面。')).toBeInTheDocument()
    expect(screen.queryByText(/Dashboard/)).not.toBeInTheDocument()
  })

  it.each([
    ['authorization_denied', '你已取消 Twitch 授權。'],
    ['provider_unavailable', 'Twitch 授權暫時無法使用。'],
    ['bot_invite_wrong_account', '請使用指定的 Bot 帳號完成授權。'],
    ['bot_account_missing_scopes', 'Bot 權限未完整授予。'],
    ['bot_account_role_conflict', '這個 Twitch 帳號已作為 Niibot 實況主使用。'],
  ])('shows only actionable bot authorization failure copy for %s', (reason, message) => {
    render(
      <MemoryRouter initialEntries={[`/bot-auth/result?status=error&reason=${reason}`]}>
        <BotAuthorizationResult />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: 'Bot 授權未完成' })).toBeInTheDocument()
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

      expect(screen.getByText('Bot 授權未完成，請重新取得授權連結。')).toBeInTheDocument()
      expect(screen.queryByText(reason)).not.toBeInTheDocument()
    }
  )
})
