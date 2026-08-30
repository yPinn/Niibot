import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import Landing from './Landing'

const setTheme = vi.fn()
let resolvedTheme: 'dark' | 'light' = 'dark'

if (!globalThis.IntersectionObserver) {
  globalThis.IntersectionObserver = class {
    root = null
    rootMargin = ''
    thresholds = []
    disconnect() {}
    observe() {}
    takeRecords() {
      return []
    }
    unobserve() {}
  }
}

vi.mock('@/components/layout/theme-provider', () => ({
  useTheme: () => ({ resolvedTheme, setTheme }),
}))
vi.mock('@/hooks/useDocumentTitle')

describe('Landing', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resolvedTheme = 'dark'
  })

  it('keeps the primary start action in the top navigation', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<div>登入頁面</div>} />
        </Routes>
      </MemoryRouter>
    )

    const navigation = screen.getByRole('navigation', { name: '主要導覽' })
    await user.click(within(navigation).getByRole('link', { name: '開始使用' }))

    expect(screen.getByText('登入頁面')).toBeInTheDocument()
  })

  it('uses a viewport-sized slide deck with a stable content order', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    const deck = screen.getByTestId('landing-deck')
    expect(deck).toHaveClass('overflow-y-auto', 'snap-y', 'snap-mandatory')

    const slides = screen.getAllByTestId('landing-slide')
    expect(slides).toHaveLength(4)
    for (const slide of slides) expect(slide).toHaveClass('min-h-full', 'snap-start')

    expect(slides.map(slide => slide.querySelector('h1, h2')?.textContent)).toEqual([
      'Niibot',
      'Video Queue',
      '聊天室互動',
      '其他功能',
    ])
  })

  it('keeps the character introduction concise and factual', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { level: 1, name: 'Niibot' })).toBeInTheDocument()
    expect(screen.getByText('Twitch 直播小幫手｜泥爸')).toBeInTheDocument()
    expect(screen.getByText('沒有勞基法保障的虛擬社畜。')).toHaveClass('block')
    expect(screen.getByText('沒有薪水，沒有休假，只有一個使命：')).toHaveClass('block')
    const mission = screen.getByText('讓你的聊天室繼續活著。')
    expect(mission.tagName).toBe('STRONG')
    expect(mission).toHaveClass('block', 'text-foreground')
    expect(mission).not.toHaveClass('text-primary')

    const hero = screen.getAllByTestId('landing-slide')[0]
    expect(within(hero).getByRole('link', { name: '開始使用' })).toHaveAttribute('href', '/login')

    const portrait = within(hero).getByRole('img', { name: 'Niibot 泥爸頭像' }).parentElement
    expect(portrait).toHaveClass('size-40', 'sm:size-52', 'lg:size-72')
    expect(screen.queryByText(/直播的大小事|不是綁死的套餐/)).not.toBeInTheDocument()
  })

  it('presents the real Video Queue workflow without a marketing slogan', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    const showcase = screen.getByRole('region', { name: 'Video Queue 功能展示' })
    expect(within(showcase).getByRole('heading', { name: 'Video Queue' })).toBeInTheDocument()
    expect(within(showcase).getByText('觀眾投稿')).toBeInTheDocument()
    expect(within(showcase).getByText('Dashboard 管理')).toBeInTheDocument()
    expect(within(showcase).getByText('OBS 播放')).toBeInTheDocument()
    expect(within(showcase).getByText('YouTube')).toBeInTheDocument()
    expect(within(showcase).getByText('Bilibili')).toBeInTheDocument()
    expect(within(showcase).getByText('Twitch Clip')).toBeInTheDocument()

    const overlayPreview = within(showcase).getByLabelText('OBS Overlay 外觀示意')
    expect(within(overlayPreview).getByText('@ momo')).toBeInTheDocument()
    expect(within(overlayPreview).getByLabelText('剩餘時間 03:42')).toBeInTheDocument()
    expect(
      within(overlayPreview).getByRole('img', { name: 'OBS Overlay 影片內容示意' })
    ).toBeInTheDocument()
    expect(showcase.querySelector('iframe')).not.toBeInTheDocument()
  })

  it('uses explicit alignment axes inside showcase blocks', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    const showcase = screen.getByRole('region', { name: 'Video Queue 功能展示' })
    expect(within(showcase).getByTestId('video-queue-layout')).toHaveClass(
      'lg:grid-cols-[minmax(0,1.2fr)_minmax(22rem,0.8fr)]'
    )

    for (const item of within(showcase).getAllByRole('listitem').slice(0, 3)) {
      expect(item).toHaveClass('sm:grid-cols-[2rem_minmax(0,1fr)]')
    }

    const queueHeader = within(showcase).getByText('等待佇列').closest('[data-slot="card-header"]')
    expect(queueHeader).toHaveClass('items-center')
    expect(queueHeader?.querySelector('[data-slot="card-action"]')).toHaveClass('self-center')

    const commandRow = screen.getByText('!ai 今天吃什麼').parentElement
    expect(commandRow).toHaveClass('items-baseline')
  })

  it('groups the remaining capabilities by need without inventing template imports', () => {
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    expect(screen.getByRole('heading', { level: 2, name: '聊天室互動' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '其他功能' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '直播流程' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '社群延伸' })).toBeInTheDocument()
    expect(screen.queryByText(/模板匯入/)).not.toBeInTheDocument()
  })

  it('exposes an accessible theme control and legal links', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: '切換至淺色主題' }))
    expect(setTheme).toHaveBeenCalledWith('light')
    expect(screen.getByRole('link', { name: '服務條款' })).toHaveAttribute('href', '/terms')
    expect(screen.getByRole('link', { name: '隱私權政策' })).toHaveAttribute('href', '/privacy')
  })

  it('offers the inverse theme action when the page is light', async () => {
    const user = userEvent.setup()
    resolvedTheme = 'light'
    render(
      <MemoryRouter>
        <Landing />
      </MemoryRouter>
    )

    await user.click(screen.getByRole('button', { name: '切換至深色主題' }))
    expect(setTheme).toHaveBeenCalledWith('dark')
  })
})
