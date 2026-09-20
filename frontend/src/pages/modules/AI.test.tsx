import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const tenantState = vi.hoisted(() => ({
  activeTenant: {
    channel_id: 'channel-a',
    channel_name: 'alice',
    display_name: 'Alice',
    enabled: true,
    role: 'owner',
    capabilities: ['edit_operations'],
  },
}))

vi.mock('@/api/aiSettings', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return {
    ...actual,
    getTenantAISettings: vi.fn(),
    patchTenantAISettings: vi.fn(),
    resetTenantAISettings: vi.fn(),
  }
})
vi.mock('@/api/analytics', () => ({ getChannelBadges: vi.fn() }))
vi.mock('@/api/emotes', () => ({ getTenantChannelEmotes: vi.fn() }))
vi.mock('@/api/roleplay', async importOriginal => {
  const actual = (await importOriginal()) as Record<string, unknown>
  return { ...actual, listRoleplaySets: vi.fn(), usePersonaMode: vi.fn() }
})
vi.mock('@/contexts/TenantContext', () => ({
  useTenant: () => tenantState,
}))
vi.mock('@/contexts/ServiceStatusContext', () => ({
  useServiceStatus: () => ({ twitch: { ai_model: 'groq/test-model' } }),
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { AI_SETTINGS_DEFAULT, getTenantAISettings, patchTenantAISettings } from '@/api/aiSettings'
import { getChannelBadges } from '@/api/analytics'
import { getTenantChannelEmotes } from '@/api/emotes'
import { listRoleplaySets } from '@/api/roleplay'

import AIModule from './AI'

describe('AI persona and short-term memory settings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    tenantState.activeTenant = {
      channel_id: 'channel-a',
      channel_name: 'alice',
      display_name: 'Alice',
      enabled: true,
      role: 'owner',
      capabilities: ['edit_operations'],
    }
    vi.mocked(getTenantAISettings).mockResolvedValue(AI_SETTINGS_DEFAULT)
    vi.mocked(getTenantChannelEmotes).mockResolvedValue({
      bot_user_id: 'bot-1',
      bot_token_available: true,
      emotes: [],
      other_channels: [],
    })
    vi.mocked(getChannelBadges).mockResolvedValue({
      subscriber_1m: null,
      founder: null,
      sets: { subscriber: [], founder: [], bits: [] },
    })
    vi.mocked(patchTenantAISettings).mockImplementation(async (_channelId, patch) => ({
      ...AI_SETTINGS_DEFAULT,
      ...patch,
    }))
    vi.mocked(listRoleplaySets).mockResolvedValue([])
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
      expect(patchTenantAISettings).toHaveBeenCalledWith(
        'channel-a',
        expect.objectContaining({
          self_pronoun: '本機器人',
          example_replies: ['簡單來說，答案是這個。'],
          memory_enabled: true,
        })
      )
    })
    expect(vi.mocked(patchTenantAISettings).mock.calls[0][1]).not.toHaveProperty(
      'audience_reference'
    )
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
    vi.mocked(getTenantAISettings).mockResolvedValue({
      ...AI_SETTINGS_DEFAULT,
      refusal_style: 'humorous',
    })
    const user = userEvent.setup()
    render(<AIModule />)

    await user.click(await screen.findByRole('button', { name: '元氣明快親切，適度鼓勵' }))
    await user.click(screen.getAllByRole('button', { name: '儲存' })[0])

    await waitFor(() => {
      expect(patchTenantAISettings).toHaveBeenCalledWith(
        'channel-a',
        expect.objectContaining({
          tone_preset: 'energetic',
          refusal_style: 'humorous',
        })
      )
    })
  })

  it('changes editor tabs without changing the active runtime mode', async () => {
    const user = userEvent.setup()
    render(<AIModule />)

    expect(await screen.findByText('說話風格使用中')).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: '故事角色' }))

    expect(await screen.findByText('還沒有故事角色')).toBeInTheDocument()
    expect(screen.getByText('說話風格使用中')).toBeInTheDocument()
  })

  it('shows a recoverable settings error instead of editable fallback values', async () => {
    const user = userEvent.setup()
    vi.mocked(getTenantAISettings)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(AI_SETTINGS_DEFAULT)

    render(<AIModule />)

    expect(await screen.findByText('無法載入 AI 設定')).toBeInTheDocument()
    expect(screen.queryByLabelText('Bot 名稱')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新載入' }))

    expect(await screen.findByLabelText('Bot 名稱')).toHaveValue(AI_SETTINGS_DEFAULT.bot_name)
  })

  it('ignores stale settings when the managed channel changes', async () => {
    let resolveFirst: ((settings: typeof AI_SETTINGS_DEFAULT) => void) | undefined
    const first = new Promise<typeof AI_SETTINGS_DEFAULT>(resolve => {
      resolveFirst = resolve
    })
    vi.mocked(getTenantAISettings)
      .mockReturnValueOnce(first)
      .mockResolvedValueOnce({ ...AI_SETTINGS_DEFAULT, bot_name: 'Channel B Bot' })
    const { rerender } = render(<AIModule />)

    tenantState.activeTenant = {
      ...tenantState.activeTenant,
      channel_id: 'channel-b',
      channel_name: 'bob',
      display_name: 'Bob',
    }
    rerender(<AIModule />)

    await waitFor(() => expect(screen.getByLabelText('Bot 名稱')).toHaveValue('Channel B Bot'))
    resolveFirst?.({ ...AI_SETTINGS_DEFAULT, bot_name: 'Stale Channel A Bot' })
    await waitFor(() => expect(screen.getByLabelText('Bot 名稱')).toHaveValue('Channel B Bot'))
  })

  it('loads tenant emotes for managers without requesting owner-only badges', async () => {
    tenantState.activeTenant = { ...tenantState.activeTenant, role: 'manager' }

    render(<AIModule />)

    await screen.findByLabelText('Bot 名稱')
    expect(getTenantChannelEmotes).toHaveBeenCalledWith('channel-a')
    expect(getChannelBadges).not.toHaveBeenCalled()
  })
})
