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

  it('presents Twitch chat management as the primary use case', () => {
    render(
      <MemoryRouter>
        <LoginForm />
      </MemoryRouter>
    )

    expect(screen.getByText('先用 Twitch 登入，開始設定你的直播聊天室。')).toBeInTheDocument()
    expect(screen.getByText('設定聊天室指令與自動回覆')).toBeInTheDocument()
    expect(screen.getByText('在追隨、訂閱、突襲與忠誠點數兌換時自動回覆')).toBeInTheDocument()
    expect(screen.getByText('依需求加入排隊、直播畫面與 Discord 工具')).toBeInTheDocument()
    expect(screen.getByText('會前往 Twitch 完成登入，再回到 Niibot。')).toBeInTheDocument()
  })
})
