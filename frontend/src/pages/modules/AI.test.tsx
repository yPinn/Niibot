import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/aiSettings', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    getAISettings: vi.fn(),
    patchAISettings: vi.fn(),
    resetAISettings: vi.fn(),
  }
})
vi.mock('@/api/analytics', () => ({ getChannelBadges: vi.fn() }))
vi.mock('@/api/emotes', () => ({ getChannelEmotes: vi.fn() }))
vi.mock('@/contexts/ServiceStatusContext', () => ({
  useServiceStatus: () => ({ twitch: { ai_model: 'groq/test-model' } }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { AI_SETTINGS_DEFAULT, getAISettings, patchAISettings } from '@/api/aiSettings'
import { getChannelBadges } from '@/api/analytics'
import { getChannelEmotes } from '@/api/emotes'

import AIModule from './AI'

describe('AI persona and short-term memory settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getAISettings).mockResolvedValue(AI_SETTINGS_DEFAULT)
    vi.mocked(getChannelEmotes).mockResolvedValue({
      bot_user_id: 'bot-1',
      bot_token_available: true,
      emotes: [],
    })
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

    const selfPronoun = screen.getByLabelText('自稱')
    await user.clear(selfPronoun)
    await user.type(selfPronoun, '本機器人')
    await user.type(screen.getByLabelText('示例回覆 1'), '簡單來說，答案是這個。')
    await user.click(memory)

    const save = screen.getAllByRole('button', { name: '儲存' })[0]
    await user.click(save)

    await waitFor(() => {
      expect(patchAISettings).toHaveBeenCalledWith(
        expect.objectContaining({
          self_pronoun: '本機器人',
          example_replies: ['簡單來說，答案是這個。'],
          memory_enabled: true,
        })
      )
    })
    expect(vi.mocked(patchAISettings).mock.calls[0][0]).not.toHaveProperty('audience_reference')
  })

  it('explains that persona fields are optional style references', async () => {
    render(<AIModule />)

    expect(
      await screen.findByText(/先把答案說清楚，再自然帶入角色；避免要求每句都表演/)
    ).toBeInTheDocument()
    expect(screen.getByText(/模型只參考語氣與節奏，不會把示例當成固定台詞/)).toBeInTheDocument()
    expect(screen.queryByLabelText('對全體稱呼')).not.toBeInTheDocument()
  })

  it('uses outcome-based setting labels and explains channel-wide cooldown', async () => {
    render(<AIModule />)

    expect(await screen.findByText('角色範本')).toBeInTheDocument()
    expect(screen.getByText(/套用後仍可微調下方欄位；不會改變婉拒方式/)).toBeInTheDocument()
    expect(screen.getByText('口頭禪頻率')).toBeInTheDocument()
    expect(screen.getByText('回覆語氣')).toBeInTheDocument()
    expect(screen.getByText('回覆語言')).toBeInTheDocument()
    expect(screen.getByText('婉拒方式')).toBeInTheDocument()
    expect(screen.getByText('頻道冷卻時間')).toBeInTheDocument()
    expect(screen.getByText(/任一觀眾使用後，全頻道需等待/)).toBeInTheDocument()
    expect(screen.getByText('誰可以使用')).toBeInTheDocument()
    expect(screen.getByLabelText('頻道冷卻時間（秒）')).toHaveValue(30)
  })

  it('keeps refusal behavior independent when applying a persona preset', async () => {
    vi.mocked(getAISettings).mockResolvedValue({
      ...AI_SETTINGS_DEFAULT,
      refusal_style: 'humorous',
    })
    const user = userEvent.setup()
    render(<AIModule />)

    await user.click(await screen.findByRole('button', { name: '元氣明快親切，適度鼓勵' }))
    await user.click(screen.getAllByRole('button', { name: '儲存' })[0])

    await waitFor(() => {
      expect(patchAISettings).toHaveBeenCalledWith(
        expect.objectContaining({
          tone_preset: 'energetic',
          refusal_style: 'humorous',
        })
      )
    })
  })
})
