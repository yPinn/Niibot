import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/aiSettings', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    getAIEmotes: vi.fn(),
    getAISettings: vi.fn(),
    patchAISettings: vi.fn(),
    resetAISettings: vi.fn(),
  }
})
vi.mock('@/api/analytics', () => ({ getChannelBadges: vi.fn() }))
vi.mock('@/contexts/ServiceStatusContext', () => ({
  useServiceStatus: () => ({ twitch: { ai_model: 'groq/test-model' } }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { AI_SETTINGS_DEFAULT, getAIEmotes, getAISettings, patchAISettings } from '@/api/aiSettings'
import { getChannelBadges } from '@/api/analytics'

import AIModule from './AI'

describe('AI persona and short-term memory settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAISettings).mockResolvedValue(AI_SETTINGS_DEFAULT)
    vi.mocked(getAIEmotes).mockResolvedValue([])
    vi.mocked(getChannelBadges).mockResolvedValue({
      subscriber_1m: null,
      founder: null,
      sets: { subscriber: [], founder: [], bits: [] },
    })
    vi.mocked(patchAISettings).mockImplementation(async patch => ({
      ...AI_SETTINGS_DEFAULT,
      ...patch,
    }))
  })

  it('keeps memory opt-in and saves structured persona examples', async () => {
    const user = userEvent.setup()
    render(<AIModule />)

    const memory = await screen.findByRole('switch', {
      name: '短期對話記憶（實驗性）',
    })
    expect(memory).not.toBeChecked()
    expect(screen.getByText(/最近 2 輪，10 分鐘後失效/)).toBeInTheDocument()

    const audience = screen.getByLabelText('觀眾稱呼')
    await user.clear(audience)
    await user.type(audience, '聊天室')
    await user.type(screen.getByLabelText('示例回覆 1'), '簡單來說，答案是這個。')
    await user.click(memory)

    const save = screen.getAllByRole('button', { name: '儲存' })[0]
    await user.click(save)

    await waitFor(() => {
      expect(patchAISettings).toHaveBeenCalledWith(
        expect.objectContaining({
          audience_reference: '聊天室',
          example_replies: ['簡單來說，答案是這個。'],
          memory_enabled: true,
        })
      )
    })
  })
})
