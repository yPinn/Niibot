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

  const renderInvite = () =>
    render(
      <MemoryRouter initialEntries={['/bot-invite/opaque?nonce=state-nonce']}>
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
    expect(screen.getByText(/想在自己的頻道，用你的 Twitch 帳號當聊天機器人/)).toBeInTheDocument()
    // plain-language capability summary, not raw scope codes
    expect(screen.getByText(/發送機器人回覆與指令/)).toBeInTheDocument()
    // disclosures Twitch's own consent screen cannot make
    expect(screen.getByText(/不會建立 Niibot 帳號/)).toBeInTheDocument()
    expect(screen.getByText(/拿不到你的 Twitch 密碼/)).toBeInTheDocument()
    expect(screen.getByText(/一次性使用/)).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
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

  it('renders a standalone success result without entering the dashboard', () => {
    render(
      <MemoryRouter initialEntries={['/bot-auth/result?status=success']}>
        <BotAuthorizationResult />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: 'Bot 授權完成' })).toBeInTheDocument()
    expect(screen.getByText('你可以關閉這個頁面。')).toBeInTheDocument()
    expect(screen.queryByText(/Dashboard/)).not.toBeInTheDocument()
  })
})
