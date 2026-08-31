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

  it('shows only consent context, requested scopes, and explicit approve or decline actions', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/bot-invite/opaque?nonce=state-nonce']}>
        <Routes>
          <Route path="/bot-invite/:publicToken" element={<BotInvite />} />
        </Routes>
      </MemoryRouter>
    )

    expect(await screen.findByRole('heading', { name: '授權 Bot 帳號' })).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('user:bot')).toBeInTheDocument()
    expect(screen.getByText('user:write:chat')).toBeInTheDocument()
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前往 Twitch 授權' })).toHaveAttribute(
      'href',
      'https://id.twitch.tv/oauth2/authorize?safe=1'
    )

    await user.click(screen.getByRole('button', { name: '拒絕邀請' }))

    await waitFor(() => expect(mockDeclineBotInvite).toHaveBeenCalledWith('opaque', 'state-nonce'))
    expect(await screen.findByText('已拒絕這次 Bot 授權邀請')).toBeInTheDocument()
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
