import { MemoryRouter } from 'react-router-dom'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api', () => ({
  openTwitchOAuth: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

import { openTwitchOAuth } from '@/api'

import { LoginForm } from './login-form'

describe('LoginForm', () => {
  beforeEach(() => {
    vi.mocked(openTwitchOAuth).mockReset()
    vi.mocked(toast.error).mockReset()
    vi.mocked(toast.warning).mockReset()
  })

  it('reports OAuth startup failures instead of leaving a rejected promise unhandled', async () => {
    vi.mocked(openTwitchOAuth).mockRejectedValue(new Error('登入服務暫時無法使用，請稍後再試'))
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <LoginForm />
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: '使用 Twitch 登入' }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('無法啟動 Twitch 登入', {
        description: '登入服務暫時無法使用，請稍後再試',
      })
    )
  })
})
