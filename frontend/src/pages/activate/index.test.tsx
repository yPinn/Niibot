import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, type MockedFunction, vi } from 'vitest'

import { getActivationRequestStatus } from '@/api/user'
import { useAuth } from '@/contexts/AuthContext'
import ActivatePage from '@/pages/activate'

vi.mock('@/api/user', () => ({
  activateAccount: vi.fn(),
  getActivationRequestStatus: vi.fn(),
  getPendingActivationCode: vi.fn(),
}))
vi.mock('@/contexts/AuthContext')
vi.mock('@/hooks/useDocumentTitle')

const mockUseAuth = useAuth as MockedFunction<typeof useAuth>
const mockGetActivationRequestStatus = getActivationRequestStatus as MockedFunction<
  typeof getActivationRequestStatus
>

function makeAuthValue(
  overrides: Partial<ReturnType<typeof useAuth>> = {}
): ReturnType<typeof useAuth> {
  return {
    user: null,
    isAuthenticated: false,
    isInitialized: false,
    isInitError: false,
    isAffiliate: false,
    channels: [],
    logout: vi.fn(),
    refreshUser: vi.fn(),
    refreshChannels: vi.fn(),
    retryInit: vi.fn(),
    ...overrides,
  }
}

describe('ActivatePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseAuth.mockReturnValue(makeAuthValue())
  })

  it('renders the supplied creator identity and activation guidance in preview mode', () => {
    render(
      <MemoryRouter>
        <ActivatePage preview />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { name: '啟用你的帳號' })).toBeInTheDocument()
    expect(screen.getByText('使用 Twitch 獎勵或啟用碼完成啟用。')).toBeInTheDocument()

    const creatorBlock = screen.getByRole('region', { name: 'Twitch 獎勵啟用' })
    expect(within(creatorBlock).getByText('皮先森ツ')).toBeInTheDocument()
    expect(within(creatorBlock).getByText('@llazypilot · Niibot 作者')).toBeInTheDocument()
    expect(
      within(creatorBlock).getByText('在 Twitch 兌換「Niibot」獎勵後，回到這裡確認。')
    ).toBeInTheDocument()
    expect(within(creatorBlock).queryByText(/啟用資格在我的/)).not.toBeInTheDocument()

    const twitchLink = within(creatorBlock).getByRole('link', { name: '前往 Twitch 兌換' })
    expect(twitchLink).toHaveAttribute('href', 'https://www.twitch.tv/llazypilot')

    expect(creatorBlock.querySelector('[data-slot="avatar"]')).toBeInTheDocument()
    expect(twitchLink).toHaveAttribute('data-slot', 'button')
    expect(
      within(creatorBlock).getByText('需要協助？前往 Discord 社群').closest('[data-slot="button"]')
    ).toBeTruthy()
    expect(within(creatorBlock).getByRole('button', { name: '確認是否已啟用' })).toBeInTheDocument()

    const codeBlock = screen.getByRole('region', { name: '啟用碼' })
    expect(codeBlock.parentElement).toHaveClass('pb-card')
    expect(codeBlock).toHaveClass('bg-muted', 'rounded-lg')
    expect(creatorBlock).toHaveClass('bg-muted', 'rounded-lg')
    expect(within(codeBlock).getByText('輸入作者提供的 6 位數啟用碼。')).toBeInTheDocument()
    expect(within(codeBlock).getByRole('button', { name: '使用啟用碼' })).toBeInTheDocument()
    expect(screen.getByText('或')).toBeInTheDocument()
    expect(mockGetActivationRequestStatus).not.toHaveBeenCalled()
  })

  it('reveals a shared OTP control and full-width code actions', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ActivatePage preview />
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: '使用啟用碼' }))

    const codeSection = screen.getByRole('region', { name: '啟用碼' })
    expect(within(codeSection).getByRole('button', { name: '查看啟用碼' })).toHaveClass('w-full')
    expect(within(codeSection).getByRole('button', { name: '啟用帳號' })).toHaveClass('w-full')
    expect(codeSection.querySelector('[data-slot="input-otp"]')).toBeInTheDocument()
    expect(codeSection.querySelectorAll('[data-slot="input-otp-slot"]')).toHaveLength(6)

    const otpInput = within(codeSection).getByRole('textbox', { name: '6 位啟用碼' })
    fireEvent.change(otpInput, { target: { value: 'abc' } })
    expect(otpInput).toHaveValue('')
    fireEvent.change(otpInput, { target: { value: '123' } })
    expect(otpInput).toHaveValue('123')
  })

  it('keeps the production unauthenticated redirect intact', () => {
    mockUseAuth.mockReturnValue(makeAuthValue({ isInitialized: true }))

    render(
      <MemoryRouter initialEntries={['/activate']}>
        <Routes>
          <Route path="/activate" element={<ActivatePage />} />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </MemoryRouter>
    )

    expect(screen.getByText('Login Page')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '啟用你的帳號' })).not.toBeInTheDocument()
  })
})
