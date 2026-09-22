import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/communityOverlay', () => ({
  DEFAULT_COMMUNITY_OVERLAY_THEME: {
    surface_color: '#FFF7CF',
    accent_color: '#EF4D88',
    text_color: '#241B34',
    placement: 'bottom-left',
    radius_px: 24,
    display_ms: 5000,
    motion: 'standard',
  },
  DEFAULT_TAROT_OVERLAY_THEME: {
    surface_color: '#FFF7CF',
    accent_color: '#EF4D88',
    text_color: '#241B34',
    placement: 'bottom-left',
    radius_px: 16,
    display_ms: 5000,
    motion: 'standard',
  },
  getCommunityOverlaySettings: vi.fn(),
  getCommunityOverlayThemeSettings: vi.fn(),
  publishCommunityOverlayTheme: vi.fn(),
  resetCommunityOverlayThemeDraft: vi.fn(),
  rotateCommunityOverlayKey: vi.fn(),
  triggerCommunityOverlayPreview: vi.fn(),
  updateCommunityOverlayThemeDraft: vi.fn(),
  updateCommunityOverlaySettings: vi.fn(),
}))
vi.mock('@/api/events', () => ({
  getRedemptionConfigs: vi.fn(),
  getTwitchRewards: vi.fn(),
  updateRedemptionConfig: vi.fn(),
  NonPartnerError: class NonPartnerError extends Error {},
}))
vi.mock('@/hooks/useDocumentTitle', () => ({ useDocumentTitle: vi.fn() }))
vi.mock('@/lib/clipboard', () => ({ copyToClipboard: vi.fn() }))
vi.mock('@/lib/toast-error', () => ({ toastApiError: vi.fn() }))
vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

import { toast } from 'sonner'

import {
  type CommunityOverlayAccess,
  type CommunityOverlayThemeState,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
  getCommunityOverlaySettings,
  getCommunityOverlayThemeSettings,
  publishCommunityOverlayTheme,
  resetCommunityOverlayThemeDraft,
  rotateCommunityOverlayKey,
  triggerCommunityOverlayPreview,
  updateCommunityOverlaySettings,
  updateCommunityOverlayThemeDraft,
} from '@/api/communityOverlay'
import {
  getRedemptionConfigs,
  getTwitchRewards,
  NonPartnerError,
  updateRedemptionConfig,
} from '@/api/events'
import { copyToClipboard } from '@/lib/clipboard'
import { toastApiError } from '@/lib/toast-error'

import CommunityOverlaySettings from './CommunityOverlaySettings'

const KEY = '11111111-1111-4111-8111-111111111111'
const NEW_KEY = '22222222-2222-4222-8222-222222222222'
const ACCESS: CommunityOverlayAccess = {
  public_key: KEY,
  enabled: true,
  created_at: '2026-08-31T10:00:00Z',
  updated_at: '2026-08-31T10:00:00Z',
}
const THEME_STATE: CommunityOverlayThemeState = {
  block_type: 'checkin',
  renderer: 'checkin-card',
  schema_version: 1,
  draft_version: 1,
  draft: DEFAULT_COMMUNITY_OVERLAY_THEME,
  published: {
    revision_id: 41,
    renderer: 'checkin-card',
    schema_version: 1,
    theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
    created_at: '2026-08-31T10:00:00Z',
  },
  has_unpublished_changes: false,
  updated_at: '2026-08-31T10:00:00Z',
}
const TAROT_THEME_STATE: CommunityOverlayThemeState = {
  ...THEME_STATE,
  block_type: 'tarot',
  renderer: 'tarot-card',
  draft: DEFAULT_TAROT_OVERLAY_THEME,
  published: {
    ...THEME_STATE.published,
    renderer: 'tarot-card',
    theme: DEFAULT_TAROT_OVERLAY_THEME,
  },
}
const CHECKIN_REDEMPTION = {
  id: 8,
  channel_id: 'channel-1',
  action_type: 'checkin',
  reward_name: '每日簽到',
  reward_id: 'reward-checkin',
  enabled: true,
}
const CHECKIN_REWARD = {
  id: 'reward-checkin',
  title: '每日簽到',
  cost: 10,
  is_enabled: true,
  is_paused: false,
  is_in_stock: true,
  should_redemptions_skip_request_queue: true,
  max_per_stream: 100,
  max_per_user_per_stream: 1,
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

describe('CommunityOverlaySettings', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getCommunityOverlaySettings).mockResolvedValue(ACCESS)
    vi.mocked(getCommunityOverlayThemeSettings).mockImplementation(async blockType =>
      blockType === 'tarot' ? TAROT_THEME_STATE : THEME_STATE
    )
    vi.mocked(updateCommunityOverlayThemeDraft).mockResolvedValue({
      ...THEME_STATE,
      has_unpublished_changes: true,
    })
    vi.mocked(publishCommunityOverlayTheme).mockResolvedValue(THEME_STATE)
    vi.mocked(resetCommunityOverlayThemeDraft).mockResolvedValue(THEME_STATE)
    vi.mocked(updateCommunityOverlaySettings).mockImplementation(async enabled => ({
      ...ACCESS,
      enabled,
    }))
    vi.mocked(rotateCommunityOverlayKey).mockResolvedValue({
      ...ACCESS,
      public_key: NEW_KEY,
    })
    vi.mocked(triggerCommunityOverlayPreview).mockImplementation(async contentType => ({
      content_type: contentType,
      event_id: 91,
    }))
    vi.mocked(getRedemptionConfigs).mockResolvedValue([CHECKIN_REDEMPTION])
    vi.mocked(getTwitchRewards).mockResolvedValue([CHECKIN_REWARD])
    vi.mocked(updateRedemptionConfig).mockResolvedValue(CHECKIN_REDEMPTION)
  })

  it('renders an isolated development preview without loading tenant settings', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings preview />)

    expect(screen.getByRole('heading', { name: 'Live Display' })).toBeInTheDocument()
    expect(getCommunityOverlaySettings).not.toHaveBeenCalled()
    expect(getCommunityOverlayThemeSettings).not.toHaveBeenCalled()

    await user.click(screen.getByRole('switch', { name: '啟用直播畫面顯示' }))
    expect(updateCommunityOverlaySettings).not.toHaveBeenCalled()
    expect(screen.getByText('已停用')).toBeInTheDocument()
  })

  it('keeps the loading skeleton aligned with the responsive workspace', () => {
    const pendingAccess = deferred<CommunityOverlayAccess>()
    vi.mocked(getCommunityOverlaySettings).mockReturnValueOnce(pendingAccess.promise)

    const { container } = render(<CommunityOverlaySettings />)

    const workspace = container.querySelector('[data-layout="live-display-workspace"]')
    expect(workspace?.closest('main')).toHaveClass('h-full', 'xl:overflow-y-hidden')
    expect(workspace).toHaveClass(
      'grid',
      'grid-cols-1',
      'xl:min-h-0',
      'xl:flex-1',
      'xl:grid-cols-12',
      'xl:grid-rows-[minmax(0,1fr)]',
      'xl:overflow-hidden'
    )
    expect(
      Array.from(workspace?.querySelectorAll('[data-layout-column]') ?? []).map(column =>
        column.getAttribute('data-layout-column')
      )
    ).toEqual(['content', 'support'])
    const content = workspace?.querySelector('[data-layout-column="content"]')
    expect(content).toHaveAttribute('data-layout-scroll', 'content')
    expect(content).toHaveClass(
      'xl:col-span-8',
      'xl:h-full',
      'xl:min-h-0',
      'xl:overflow-y-auto',
      'xl:overscroll-contain'
    )
    expect(
      Array.from(content?.querySelectorAll('[data-layout-panel]') ?? []).map(panel =>
        panel.getAttribute('data-layout-panel')
      )
    ).toEqual(['checkin', 'tarot'])
    const support = workspace?.querySelector('[data-layout-column="support"]')
    expect(support).toHaveAttribute('data-layout-position', 'fixed')
    expect(support).toHaveClass(
      'xl:col-span-4',
      'xl:sticky',
      'xl:top-0',
      'xl:max-h-full',
      'xl:overflow-y-auto'
    )
    expect(
      Array.from(support?.querySelectorAll('[data-layout-panel]') ?? []).map(panel =>
        panel.getAttribute('data-layout-panel')
      )
    ).toEqual(['connection', 'preview'])
  })

  it('aligns the first content card with OBS and keeps page guidance concise', async () => {
    render(<CommunityOverlaySettings preview />)

    expect(screen.getByText('設定直播內容與 OBS 連線。')).toBeInTheDocument()
    const content = screen.getByRole('region', { name: '顯示內容' })
    expect(within(content).getByRole('heading', { name: '顯示內容' })).toHaveClass('sr-only')
    expect(content.children[1]).toHaveAttribute('data-layout-start', 'cards')
    expect(
      within(content).queryByText('管理直播畫面要播放的內容；每項都能直接測試，不會寫入正式紀錄。')
    ).not.toBeInTheDocument()

    expect(within(content).getByText('觀眾簽到時抽卡，並顯示個人卡冊。')).toBeInTheDocument()
    expect(within(content).getByText('直播顯示牌面，完整解讀回覆在聊天室。')).toBeInTheDocument()
    expect(within(content).getByText('設定只套用到這個頻道。')).toBeInTheDocument()
    expect(within(content).getByText('預設左下，可避開右下角實況視訊。')).toBeInTheDocument()

    const connection = screen.getByRole('region', { name: 'OBS 連線' })
    expect(connection.children[0]).toHaveAttribute('data-layout-start', 'connection')
    expect(
      within(connection).getByText('將連結加入 OBS Browser Source，設定為 1920 × 1080、透明背景。')
    ).toBeInTheDocument()
    expect(screen.getByText('即時查看草稿與測試播放。')).toBeInTheDocument()
    expect(screen.getByText('發布後才會套用至 OBS。')).toBeInTheDocument()
  })

  it('routes the development check-in test to the real binder sample renderer', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings preview />)

    await user.click(screen.getByRole('button', { name: '測試每日簽到動畫' }))

    expect(screen.getByTitle('每日簽到實際播放')).toHaveAttribute(
      'src',
      `${window.location.origin}/live-display#key=${KEY}&preview=1&block=checkin&sample=checkin`
    )
    expect(triggerCommunityOverlayPreview).not.toHaveBeenCalled()
  })

  it('uses left-bottom defaults and explains the Tarot topic slots', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings preview />)

    expect(document.querySelector('[data-theme-preview]')).toHaveAttribute(
      'data-placement',
      'bottom-left'
    )
    expect(screen.getByText('5 秒')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('slider', { name: '顯示時間' }), {
      target: { value: '4500' },
    })
    expect(screen.getByText('4.5 秒')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '展開每日塔羅設定' }))

    expect(screen.getByText('每個主題每天一張')).toBeInTheDocument()
    expect(screen.getByText('同主題重查結果不變')).toBeInTheDocument()
    expect(screen.getByText('未填為綜合；可選感情、事業、財運')).toBeInTheDocument()
    expect(screen.getByText('內建牌組')).toBeInTheDocument()
    expect(screen.getByText('更新不影響歷史紀錄')).toBeInTheDocument()
    expect(screen.getByText('16px')).toBeInTheDocument()
    expect(screen.getByText('5 秒')).toBeInTheDocument()
    expect(document.querySelector('[data-theme-preview]')).toHaveAttribute(
      'data-placement',
      'bottom-left'
    )
  })

  it('previews local tenant style changes before saving or publishing', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const accent = await screen.findByLabelText('強調色')
    await user.clear(accent)
    await user.type(accent, '#112233')
    await user.click(screen.getByRole('button', { name: '左上' }))

    const card = screen.getByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')
    expect(card).toHaveStyle({ '--overlay-accent': '#112233' })
    expect(card.closest('[data-theme-preview]')).toHaveAttribute('data-placement', 'top-left')
    expect(screen.getByText('尚未儲存')).toBeInTheDocument()
    expect(updateCommunityOverlayThemeDraft).not.toHaveBeenCalled()
    expect(publishCommunityOverlayTheme).not.toHaveBeenCalled()
  })

  it('blocks invalid color syntax but only warns on low contrast', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const surface = await screen.findByLabelText('背景色')
    await user.clear(surface)
    await user.type(surface, '#123')

    expect(screen.getByText('請輸入 #RRGGBB 格式。')).toBeInTheDocument()
    expect(surface).toHaveAttribute('aria-describedby', 'overlay-surface-color-error')
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeDisabled()

    await user.clear(surface)
    await user.type(surface, '#241B34')

    expect(screen.getByText(/文字色與背景色、強調色的對比偏低/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeEnabled()

    await user.clear(surface)
    await user.type(surface, '#EF4D88')

    expect(screen.getByText(/強調色與背景色的對比偏低/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeEnabled()
  })

  it('warns when small accent text falls below 4.5:1 against the surface', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const surface = await screen.findByLabelText('背景色')
    const accent = screen.getByLabelText('強調色')
    const text = screen.getByLabelText('文字色')
    await user.clear(surface)
    await user.type(surface, '#FFFFFF')
    await user.clear(accent)
    await user.type(accent, '#777777')
    await user.clear(text)
    await user.type(text, '#000000')

    expect(screen.getByText(/強調色與背景色的對比偏低.*4.5:1/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeEnabled()
  })

  it('remounts the static final-state sample when motion strength changes', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const originalCard = await screen.findByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')
    expect(originalCard).toHaveAttribute('data-motion-state', 'final')
    expect(document.querySelector('[data-theme-preview]')).toHaveClass('aspect-video', 'w-full')
    expect(document.querySelector('[data-preview-content]')).toHaveClass('w-[660px]')
    await user.click(screen.getByRole('button', { name: '柔和' }))

    const remountedCard = screen.getByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')
    expect(remountedCard).not.toBe(originalCard)
    expect(remountedCard).toHaveAttribute('data-motion-state', 'final')
  })

  it('uniformly scales the selected quarter of a 1920 by 1080 preview canvas', async () => {
    const user = userEvent.setup()
    const rectSpy = vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue({
      bottom: 270,
      height: 270,
      left: 0,
      right: 480,
      top: 0,
      width: 480,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    try {
      render(<CommunityOverlaySettings />)

      const viewport = await screen.findByTestId('theme-preview-viewport')
      const canvas = screen.getByTestId('theme-preview-canvas')
      expect(viewport).toHaveAttribute('data-focus', 'quarter')
      expect(viewport).toHaveClass('aspect-video')
      expect(canvas).toHaveStyle({
        width: '1920px',
        height: '1080px',
        left: '0px',
        top: '-270px',
        transform: 'scale(0.5)',
      })

      await user.click(screen.getByRole('button', { name: '右上' }))
      expect(canvas).toHaveStyle({ left: '-480px', top: '0px', transform: 'scale(0.5)' })
    } finally {
      rectSpy.mockRestore()
    }
  })

  it('keeps block controls at the standard settings density', async () => {
    render(<CommunityOverlaySettings />)

    await screen.findByLabelText('背景色')
    const editor = document.querySelector('[data-layout="live-display-theme-editor"]')
    expect(editor).not.toBeNull()
    expect(within(editor as HTMLElement).getByText('外觀')).toHaveClass('text-sub')
    expect(within(editor as HTMLElement).getByText('背景色')).toHaveClass('text-sub')
    expect(within(editor as HTMLElement).getByText('設定只套用到這個頻道。')).toHaveClass(
      'text-label'
    )
    expect(within(editor as HTMLElement).getByRole('button', { name: '儲存草稿' })).toHaveClass(
      'h-8'
    )
    expect(within(editor as HTMLElement).getByRole('button', { name: '發布至 OBS' })).toHaveClass(
      'h-8'
    )
  })

  it('uses a split settings workspace with a visual screen placement selector', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    await screen.findByLabelText('背景色')
    const editor = document.querySelector('[data-layout="live-display-theme-editor"]')
    expect(editor).not.toBeNull()

    const columns = editor?.querySelector('[data-layout="live-display-theme-editor-columns"]')
    expect(columns).toHaveClass('grid', 'grid-cols-1', 'lg:grid-cols-2')
    expect(columns?.querySelector('[data-layout-panel="appearance"]')).not.toBeNull()
    expect(columns?.querySelector('[data-layout-panel="placement-motion"]')).not.toBeNull()

    const selector = within(editor as HTMLElement).getByRole('group', { name: '顯示位置' })
    expect(selector).toHaveClass('aspect-video', 'grid', 'grid-cols-2', 'grid-rows-2', 'bg-border')

    const positions = [
      ['左上', 'top-left', ['left-2', 'top-2']],
      ['右上', 'top-right', ['right-2', 'top-2']],
      ['左下', 'bottom-left', ['bottom-2', 'left-2']],
      ['右下', 'bottom-right', ['bottom-2', 'right-2']],
    ] as const

    for (const [label, value, indicatorClasses] of positions) {
      const button = within(selector).getByRole('button', { name: label })
      expect(button).toHaveAttribute('data-placement-option', value)
      expect(button).toHaveAttribute('aria-pressed', value === 'bottom-left' ? 'true' : 'false')
      expect(within(button).getByTestId(`placement-indicator-${value}`)).toHaveClass(
        ...indicatorClasses
      )
    }

    await user.click(within(selector).getByRole('button', { name: '右上' }))
    expect(within(selector).getByRole('button', { name: '右上' })).toHaveAttribute(
      'aria-pressed',
      'true'
    )
    expect(document.querySelector('[data-theme-preview]')).toHaveAttribute(
      'data-placement',
      'top-right'
    )
  })

  it('saves a complete draft before allowing publish', async () => {
    const user = userEvent.setup()
    const savedTheme = { ...DEFAULT_COMMUNITY_OVERLAY_THEME, radius_px: 12 }
    vi.mocked(updateCommunityOverlayThemeDraft).mockResolvedValueOnce({
      ...THEME_STATE,
      draft: savedTheme,
      has_unpublished_changes: true,
    })
    render(<CommunityOverlaySettings />)

    expect(await screen.findAllByText('已發布')).toHaveLength(2)
    const radius = screen.getByRole('slider', { name: '卡片圓角' })
    fireEvent.change(radius, { target: { value: '12' } })
    await user.click(screen.getByRole('button', { name: '儲存草稿' }))

    await waitFor(() => expect(updateCommunityOverlayThemeDraft).toHaveBeenCalled())
    expect(updateCommunityOverlayThemeDraft).toHaveBeenCalledWith(
      'checkin',
      expect.objectContaining({ radius_px: expect.any(Number) }),
      1
    )
    expect(screen.getByText('草稿未發布')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '發布至 OBS' })).toBeEnabled()
  })

  it('publishes a saved revision and restores the draft from published state', async () => {
    const user = userEvent.setup()
    vi.mocked(getCommunityOverlayThemeSettings).mockResolvedValueOnce({
      ...THEME_STATE,
      draft: { ...DEFAULT_COMMUNITY_OVERLAY_THEME, placement: 'top-right' },
      has_unpublished_changes: true,
    })
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('button', { name: '發布至 OBS' }))
    await waitFor(() => expect(publishCommunityOverlayTheme).toHaveBeenCalledOnce())
    expect(publishCommunityOverlayTheme).toHaveBeenCalledWith('checkin', 1)
    expect(screen.getAllByText('已發布')).toHaveLength(2)

    await user.click(screen.getByRole('button', { name: '左上' }))
    await user.click(screen.getByRole('button', { name: '還原已發布版本' }))
    await waitFor(() => expect(resetCommunityOverlayThemeDraft).toHaveBeenCalledOnce())
    expect(resetCommunityOverlayThemeDraft).toHaveBeenCalledWith('checkin', 1)
  })

  it('loads the tenant URL and uses a direct test action instead of a chat command', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    expect(await screen.findByRole('heading', { name: 'Live Display' })).toBeInTheDocument()
    expect(screen.getAllByText('已啟用').length).toBeGreaterThan(0)
    expect(screen.queryByText('!ovltest 8')).not.toBeInTheDocument()
    expect(screen.queryByTitle('每日簽到實際播放')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '測試每日簽到動畫' }))
    await waitFor(() => expect(triggerCommunityOverlayPreview).toHaveBeenCalledWith('checkin'))
    expect(toast.success).toHaveBeenCalledWith('測試動畫已送出')

    const preview = screen.getByTitle('每日簽到實際播放')
    expect(preview).toHaveAttribute(
      'src',
      `${window.location.origin}/live-display#key=${KEY}&preview=1&block=checkin`
    )

    await user.click(screen.getByRole('button', { name: '返回草稿預覽' }))
    expect(screen.getByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')).toBeInTheDocument()
    expect(screen.queryByTitle('每日簽到實際播放')).not.toBeInTheDocument()

    expect(screen.getByRole('link', { name: '開啟 OBS 顯示畫面' })).toHaveAttribute(
      'href',
      `${window.location.origin}/live-display#key=${KEY}`
    )

    await user.click(screen.getByRole('button', { name: /點擊以複製 OBS 顯示連結/ }))
    expect(copyToClipboard).toHaveBeenCalledWith(
      `${window.location.origin}/live-display#key=${KEY}`,
      '已複製',
      '複製失敗，請手動選取網址'
    )
  })

  it('automatically returns to draft once the published display duration elapses', async () => {
    const user = userEvent.setup()
    const originalSetTimeout = window.setTimeout
    let autoCloseCallback: (() => void) | null = null
    // Default checkin theme's display_ms (5000) plus the auto-close buffer (1500).
    const setTimeoutSpy = vi
      .spyOn(window, 'setTimeout')
      .mockImplementation((handler: TimerHandler, timeout?: number, ...args: unknown[]) => {
        if (timeout === 6_500) {
          autoCloseCallback = handler as () => void
          return 0 as unknown as ReturnType<typeof window.setTimeout>
        }
        return originalSetTimeout(handler as VoidFunction, timeout, ...args)
      })

    try {
      render(<CommunityOverlaySettings />)

      await user.click(await screen.findByRole('button', { name: '測試每日簽到動畫' }))
      await waitFor(() => expect(triggerCommunityOverlayPreview).toHaveBeenCalledWith('checkin'))
      expect(screen.getByTitle('每日簽到實際播放')).toBeInTheDocument()
      expect(autoCloseCallback).not.toBeNull()

      act(() => autoCloseCallback?.())

      expect(screen.queryByTitle('每日簽到實際播放')).not.toBeInTheDocument()
    } finally {
      setTimeoutSpy.mockRestore()
    }
  })

  it('keeps the test action available after a recoverable preview failure', async () => {
    const user = userEvent.setup()
    const error = new Error('preview unavailable')
    vi.mocked(triggerCommunityOverlayPreview).mockRejectedValueOnce(error)
    render(<CommunityOverlaySettings />)

    const button = await screen.findByRole('button', { name: '測試每日簽到動畫' })
    await user.click(button)

    await waitFor(() => expect(toastApiError).toHaveBeenCalledWith(error, '測試動畫送出失敗'))
    expect(button).toBeEnabled()
  })

  it('keeps settings in the content column and shares OBS plus preview in the right rail', async () => {
    render(<CommunityOverlaySettings />)

    const content = await screen.findByRole('region', { name: '顯示內容' })
    expect(within(content).getAllByRole('heading', { name: '每日簽到' })).toHaveLength(1)
    expect(within(content).getAllByRole('heading', { name: '每日塔羅' })).toHaveLength(1)
    expect(within(content).getByRole('button', { name: '測試每日簽到動畫' })).toBeInTheDocument()
    expect(within(content).getByRole('button', { name: '儲存草稿' })).toBeInTheDocument()
    expect(within(content).queryAllByText('草稿預覽')).toHaveLength(0)
    expect(content.querySelector('[data-theme-preview]')).not.toBeInTheDocument()
    expect(within(content).queryByRole('button', { name: '返回草稿預覽' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '卡片樣式' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: '預覽與測試' })).not.toBeInTheDocument()

    const connection = screen.getByRole('region', { name: 'OBS 連線' })
    expect(within(connection).getByRole('switch', { name: '啟用直播畫面顯示' })).toBeInTheDocument()
    expect(within(connection).getByText('OBS 連線')).toBeInTheDocument()
    expect(within(connection).getByRole('button', { name: '更新連結' })).toBeInTheDocument()

    const preview = screen.getByRole('region', { name: '預覽' })
    expect(within(preview).getByText('每日簽到')).toBeInTheDocument()
    expect(within(preview).getAllByText('草稿預覽')).toHaveLength(2)
    expect(
      within(preview).getByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')
    ).toBeInTheDocument()

    const workspace = content.parentElement
    expect(workspace).toHaveAttribute('data-layout', 'live-display-workspace')
    expect(workspace?.closest('main')).toHaveClass('h-full', 'xl:overflow-y-hidden')
    expect(workspace).toHaveClass(
      'grid',
      'grid-cols-1',
      'xl:min-h-0',
      'xl:flex-1',
      'xl:grid-cols-12',
      'xl:grid-rows-[minmax(0,1fr)]',
      'xl:overflow-hidden'
    )
    expect(content).toHaveAttribute('data-layout-column', 'content')
    expect(content).toHaveAttribute('data-layout-scroll', 'content')
    expect(content).toHaveClass(
      'xl:col-span-8',
      'xl:h-full',
      'xl:min-h-0',
      'xl:overflow-y-auto',
      'xl:overscroll-contain'
    )
    const support = connection.parentElement
    expect(support).toHaveAttribute('data-layout-column', 'support')
    expect(support).toHaveAttribute('data-layout-position', 'fixed')
    expect(support).toHaveClass(
      'xl:col-span-4',
      'xl:sticky',
      'xl:top-0',
      'xl:max-h-full',
      'xl:overflow-y-auto'
    )
    expect(preview.parentElement).toBe(support)

    const themeEditor = document.querySelector('[data-layout="live-display-theme-editor"]')
    expect(themeEditor).toHaveClass('flex', 'flex-col')

    const pageRegions = screen
      .getAllByRole('region')
      .filter(region => region.getAttribute('aria-labelledby')?.startsWith('live-display-'))
    expect(
      pageRegions.map(region => within(region).getByRole('heading', { level: 2 }).textContent)
    ).toEqual(['顯示內容', 'OBS 連線', '預覽'])
    expect(screen.queryByRole('button', { name: /上移|下移/ })).not.toBeInTheDocument()
    expect(getCommunityOverlayThemeSettings).toHaveBeenCalledWith('checkin')
    expect(getCommunityOverlayThemeSettings).toHaveBeenCalledWith('tarot')
  })

  it('opens Tarot as an independent workspace and sends a Tarot preview event', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('button', { name: '展開每日塔羅設定' }))

    expect(screen.getByRole('button', { name: '收合每日塔羅設定' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '展開每日簽到設定' })).toBeInTheDocument()
    const preview = screen.getByRole('region', { name: '預覽' })
    expect(within(preview).getByText('每日塔羅')).toBeInTheDocument()
    expect(within(preview).getByLabelText('NiibotFan 的每日塔羅：愚者正位')).toBeInTheDocument()
    expect(
      within(preview).queryByLabelText('NiibotFan 的卡冊：獲得普通卡星路羅盤')
    ).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '收合每日塔羅設定' }))
    expect(within(preview).getByLabelText('NiibotFan 的每日塔羅：愚者正位')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '測試每日塔羅動畫' }))
    await waitFor(() => expect(triggerCommunityOverlayPreview).toHaveBeenCalledWith('tarot'))
    expect(screen.getByTitle('每日塔羅實際播放')).toBeInTheDocument()
  })

  it('can collapse a block without hiding its status or test action', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const content = await screen.findByRole('region', { name: '顯示內容' })
    await user.click(within(content).getByRole('button', { name: '收合每日簽到設定' }))

    expect(within(content).getByRole('heading', { name: '每日簽到' })).toBeInTheDocument()
    expect(within(content).getAllByText('已發布')).toHaveLength(2)
    expect(within(content).getByRole('button', { name: '測試每日簽到動畫' })).toBeInTheDocument()
    expect(within(content).queryByRole('button', { name: '儲存草稿' })).not.toBeInTheDocument()
    expect(within(content).getByRole('button', { name: '展開每日簽到設定' })).toBeInTheDocument()
  })

  it('shows only the necessary check-in entry summary', async () => {
    render(<CommunityOverlaySettings />)

    const trigger = await screen.findByRole('region', { name: '顯示內容' })
    expect(within(trigger).getByText('!簽到')).toBeInTheDocument()
    expect(within(trigger).getByText('每天每人記錄一次')).toBeInTheDocument()
    expect(within(trigger).getAllByText(/每日簽到/).length).toBeGreaterThan(0)
    expect(within(trigger).getByText(/10 點/)).toBeInTheDocument()
    expect(within(trigger).getByText('由 Twitch 管理獎勵')).toBeInTheDocument()
    expect(within(trigger).getByText('已啟用')).toBeInTheDocument()
    expect(within(trigger).queryByRole('combobox')).not.toBeInTheDocument()
    expect(within(trigger).queryByRole('switch')).not.toBeInTheDocument()
    expect(within(trigger).getByRole('link', { name: '管理簽到入口' })).toHaveAttribute(
      'href',
      '/channel-points'
    )
    expect(within(trigger).queryByText(/Niibot 不會建立/)).not.toBeInTheDocument()
  })

  it('keeps Channel Points as the only reward-binding editor', async () => {
    render(<CommunityOverlaySettings />)

    await screen.findByRole('link', { name: '管理簽到入口' })
    expect(updateRedemptionConfig).not.toHaveBeenCalled()
  })

  it('treats a channel without Channel Points as a normal read-only state', async () => {
    vi.mocked(getTwitchRewards).mockRejectedValueOnce(new NonPartnerError())
    render(<CommunityOverlaySettings />)

    expect(await screen.findByText('頻道點數尚不可用')).toBeInTheDocument()
    expect(screen.getByText(/仍可用聊天指令簽到/)).toBeInTheDocument()
    expect(screen.queryByText('無法載入 Twitch 簽到設定')).not.toBeInTheDocument()
  })

  it('isolates a Twitch reward load failure from OBS and theme settings', async () => {
    vi.mocked(getTwitchRewards).mockRejectedValueOnce(new Error('Twitch unavailable'))
    render(<CommunityOverlaySettings />)

    expect(await screen.findByText('無法載入 Twitch 簽到設定')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'OBS 連線' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: '顯示內容' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '儲存草稿' })).toBeInTheDocument()
  })

  it('updates the feed state and keeps the returned server state', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    const toggle = await screen.findByRole('switch', { name: '啟用直播畫面顯示' })
    await user.click(toggle)

    await waitFor(() => {
      expect(updateCommunityOverlaySettings).toHaveBeenCalledWith(false)
      expect(toggle).not.toBeChecked()
      expect(screen.getByText('已停用')).toBeInTheDocument()
    })
    expect(toast.success).toHaveBeenCalledWith('直播畫面顯示已停用')
  })

  it('keeps the previous enabled state when the update fails', async () => {
    const user = userEvent.setup()
    const error = new Error('update failed')
    vi.mocked(updateCommunityOverlaySettings).mockRejectedValueOnce(error)
    render(<CommunityOverlaySettings />)

    const toggle = await screen.findByRole('switch', { name: '啟用直播畫面顯示' })
    await user.click(toggle)

    await waitFor(() => {
      expect(toastApiError).toHaveBeenCalledWith(error, '更新直播畫面顯示失敗')
      expect(toggle).toBeChecked()
    })
  })

  it('locks key rotation until an enabled-state mutation settles', async () => {
    const user = userEvent.setup()
    const pending = deferred<CommunityOverlayAccess>()
    vi.mocked(updateCommunityOverlaySettings).mockReturnValueOnce(pending.promise)
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('switch', { name: '啟用直播畫面顯示' }))
    const rotate = screen.getByRole('button', { name: '更新連結' })

    expect(rotate).toBeDisabled()
    await user.click(rotate)
    expect(rotateCommunityOverlayKey).not.toHaveBeenCalled()

    pending.resolve({ ...ACCESS, enabled: false })
    await waitFor(() => expect(rotate).toBeEnabled())
  })

  it('requires confirmation before rotating the key and refreshes both URLs', async () => {
    const user = userEvent.setup()
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('button', { name: '更新連結' }))
    expect(rotateCommunityOverlayKey).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '確認更新' }))

    await waitFor(() => expect(rotateCommunityOverlayKey).toHaveBeenCalledOnce())
    await user.click(screen.getByRole('button', { name: '測試每日簽到動畫' }))
    expect(screen.getByTitle('每日簽到實際播放')).toHaveAttribute(
      'src',
      `${window.location.origin}/live-display#key=${NEW_KEY}&preview=1&block=checkin`
    )
    expect(screen.getByRole('link', { name: '開啟 OBS 顯示畫面' })).toHaveAttribute(
      'href',
      `${window.location.origin}/live-display#key=${NEW_KEY}`
    )
  })

  it('keeps the active key when rotation fails', async () => {
    const user = userEvent.setup()
    const error = new Error('rotation failed')
    vi.mocked(rotateCommunityOverlayKey).mockRejectedValueOnce(error)
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('button', { name: '更新連結' }))
    await user.click(screen.getByRole('button', { name: '確認更新' }))

    await waitFor(() => expect(toastApiError).toHaveBeenCalledWith(error, '更新 OBS 顯示連結失敗'))
    await user.click(screen.getByRole('button', { name: '測試每日簽到動畫' }))
    expect(screen.getByTitle('每日簽到實際播放')).toHaveAttribute(
      'src',
      `${window.location.origin}/live-display#key=${KEY}&preview=1&block=checkin`
    )
  })

  it('locks the enabled switch until key rotation settles', async () => {
    const user = userEvent.setup()
    const pending = deferred<CommunityOverlayAccess>()
    vi.mocked(rotateCommunityOverlayKey).mockReturnValueOnce(pending.promise)
    render(<CommunityOverlaySettings />)

    await user.click(await screen.findByRole('button', { name: '更新連結' }))
    await user.click(screen.getByRole('button', { name: '確認更新' }))
    const toggle = screen.getByRole('switch', { name: '啟用直播畫面顯示' })

    expect(toggle).toBeDisabled()
    await user.click(toggle)
    expect(updateCommunityOverlaySettings).not.toHaveBeenCalled()

    pending.resolve({ ...ACCESS, public_key: NEW_KEY })
    await waitFor(() => expect(toggle).toBeEnabled())
  })

  it('shows a recoverable load error', async () => {
    const user = userEvent.setup()
    vi.mocked(getCommunityOverlaySettings)
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(ACCESS)

    render(<CommunityOverlaySettings />)

    expect(await screen.findByText('Live Display 載入失敗')).toBeInTheDocument()
    expect(toastApiError).toHaveBeenCalledWith(expect.any(Error), 'Live Display 載入失敗')

    await user.click(screen.getByRole('button', { name: '重新載入' }))
    expect((await screen.findAllByText('已啟用')).length).toBeGreaterThan(0)
  })
})
