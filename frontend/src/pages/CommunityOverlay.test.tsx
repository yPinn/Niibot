import { MemoryRouter, useNavigate } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  getCommunityOverlayFeed,
  getCommunityOverlayTheme,
} from '@/api/communityOverlay'

import CommunityOverlay from './CommunityOverlay'

vi.mock('@/api/communityOverlay', () => ({
  DEFAULT_COMMUNITY_OVERLAY_THEME: {
    surface_color: '#FFF7CF',
    accent_color: '#EF4D88',
    text_color: '#241B34',
    placement: 'bottom-left',
    radius_px: 24,
    display_ms: 4000,
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
  getCommunityOverlayFeed: vi.fn(),
  getCommunityOverlayTheme: vi.fn(),
}))

const KEY = '11111111-1111-4111-8111-111111111111'

function event(id: number, totalDays = 8, actor = 'Alice') {
  return {
    id,
    event_type: 'checkin.recorded' as const,
    schema_version: 1,
    source: 'twitch',
    actor_display_name: actor,
    payload: { total_days: totalDays, checkin_date: '2026-08-31' },
    occurred_at: '2026-08-31T10:00:00Z',
    expires_at: '2026-08-31T10:10:00Z',
  }
}

function tarotEvent(id: number, actor = 'Alice') {
  return {
    id,
    event_type: 'tarot.drawn' as const,
    schema_version: 1,
    source: 'twitch',
    actor_display_name: actor,
    payload: {
      card_id: '0',
      card_name: '愚者',
      card_name_en: 'The Fool',
      orientation: 'upright',
      orientation_label: '正位',
      category: 'general',
      category_label: '綜合',
      keywords: ['新開始', '冒險', '自由'],
      meaning: '進入全新階段，無限可能展開。',
      advice: '保持開放心態。',
      image_path: '/images/tarot/decks/rider-waite-smith-pkt/v1/cards/major-00-the-fool.jpg',
      deck_id: 'rider-waite-smith-pkt',
      deck_version: 1,
    },
    occurred_at: '2026-08-31T10:00:00Z',
    expires_at: '2026-08-31T10:10:00Z',
  }
}

function renderOverlay(query: string) {
  return render(
    <MemoryRouter initialEntries={[`/live-display${query}`]}>
      <CommunityOverlay />
    </MemoryRouter>
  )
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => {
    resolve = done
  })
  return { promise, resolve }
}

function SwitchingOverlay() {
  const navigate = useNavigate()
  return (
    <>
      <button
        type="button"
        onClick={() => navigate('/live-display#key=22222222-2222-4222-8222-222222222222&preview=1')}
      >
        切換租戶
      </button>
      <CommunityOverlay />
    </>
  )
}

describe('CommunityOverlay', () => {
  beforeEach(() => {
    vi.mocked(getCommunityOverlayFeed).mockReset()
    vi.mocked(getCommunityOverlayTheme).mockReset()
    vi.mocked(getCommunityOverlayTheme).mockResolvedValue({
      revision_id: 41,
      renderer: 'checkin-card',
      schema_version: 1,
      theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
      created_at: '2026-08-31T10:00:00Z',
    })
  })

  it('stays transparent and does not poll without a capability key', () => {
    renderOverlay('')

    expect(getCommunityOverlayFeed).not.toHaveBeenCalled()
    expect(getCommunityOverlayTheme).not.toHaveBeenCalled()
    expect(document.querySelector('[data-overlay-card]')).not.toBeInTheDocument()
  })

  it('applies the tenant published colors, placement, radius, and motion contract', async () => {
    vi.mocked(getCommunityOverlayTheme).mockResolvedValue({
      revision_id: 42,
      renderer: 'checkin-card',
      schema_version: 1,
      theme: {
        ...DEFAULT_COMMUNITY_OVERLAY_THEME,
        surface_color: '#112233',
        accent_color: '#355070',
        text_color: '#F0F1F2',
        placement: 'top-left',
        radius_px: 8,
        motion: 'none',
      },
      created_at: '2026-08-31T10:05:00Z',
    })
    vi.mocked(getCommunityOverlayFeed).mockResolvedValue({ cursor: 21, events: [event(21)] })

    renderOverlay(`#key=${KEY}&preview=1`)

    const card = await screen.findByLabelText('Alice 的簽到集點卡')
    expect(getCommunityOverlayTheme).toHaveBeenCalledWith(KEY, 'checkin')
    expect(card.closest('main')).toHaveAttribute('data-placement', 'top-left')
    expect(card).toHaveStyle({
      '--overlay-surface': '#112233',
      '--overlay-accent': '#355070',
      '--overlay-text': '#F0F1F2',
      '--overlay-radius': '8px',
    })
    expect(card).toHaveAttribute('data-motion', 'none')
  })

  it('uses a no-replay handshake for a normal OBS source', async () => {
    vi.mocked(getCommunityOverlayFeed).mockResolvedValue({ cursor: 20, events: [] })

    renderOverlay(`#key=${KEY}`)

    await waitFor(() => expect(getCommunityOverlayFeed).toHaveBeenCalledWith(KEY, undefined))
    expect(document.querySelector('[data-overlay-card]')).not.toBeInTheDocument()
  })

  it('replays unexpired events only when preview mode is explicit', async () => {
    vi.mocked(getCommunityOverlayFeed).mockResolvedValue({ cursor: 21, events: [event(21, 8)] })

    renderOverlay(`#key=${KEY}&preview=1`)

    expect(await screen.findByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
    expect(getCommunityOverlayFeed).toHaveBeenCalledWith(KEY, 0)
    expect(screen.getByLabelText('累積第 8 天')).toBeInTheDocument()
    expect(screen.getAllByTestId('checkin-stamp')).toHaveLength(7)
    expect(
      screen.getAllByTestId('checkin-stamp').filter(node => node.dataset.filled === 'true')
    ).toHaveLength(1)
  })

  it('renders a Tarot event from the same ordered feed with its own published theme', async () => {
    vi.mocked(getCommunityOverlayTheme).mockImplementation(async (_key, blockType) => ({
      revision_id: 42,
      renderer: blockType === 'tarot' ? 'tarot-card' : 'checkin-card',
      schema_version: 1,
      theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
      created_at: '2026-08-31T10:05:00Z',
    }))
    vi.mocked(getCommunityOverlayFeed).mockResolvedValue({
      cursor: 22,
      events: [tarotEvent(22)],
    })

    renderOverlay(`#key=${KEY}&preview=1`)

    expect(await screen.findByLabelText('Alice 的每日塔羅：愚者正位')).toBeInTheDocument()
    expect(getCommunityOverlayTheme).toHaveBeenCalledWith(KEY, 'tarot')
    expect(screen.getByRole('img', { name: '愚者正位' })).toHaveAttribute(
      'src',
      tarotEvent(22).payload.image_path
    )
  })

  it('polls from the handshake cursor and renders a new event', async () => {
    vi.mocked(getCommunityOverlayFeed)
      .mockResolvedValueOnce({ cursor: 10, events: [] })
      .mockResolvedValue({ cursor: 11, events: [event(11, 3)] })

    renderOverlay(`#key=${KEY}`)

    expect(
      await screen.findByLabelText('Alice 的簽到集點卡', {}, { timeout: 2_500 })
    ).toBeInTheDocument()
    expect(getCommunityOverlayFeed).toHaveBeenNthCalledWith(1, KEY, undefined)
    expect(getCommunityOverlayFeed).toHaveBeenNthCalledWith(2, KEY, 10)
  })

  it('ignores unsupported event versions instead of breaking the renderer', async () => {
    vi.mocked(getCommunityOverlayFeed).mockResolvedValue({
      cursor: 30,
      events: [{ ...event(30), schema_version: 2 }],
    })

    renderOverlay(`#key=${KEY}&preview=1`)

    await waitFor(() => expect(getCommunityOverlayFeed).toHaveBeenCalled())
    expect(document.querySelector('[data-overlay-card]')).not.toBeInTheDocument()
  })

  it('refreshes a newly published theme without remounting the OBS page', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(getCommunityOverlayTheme)
        .mockResolvedValueOnce({
          revision_id: 41,
          renderer: 'checkin-card',
          schema_version: 1,
          theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
          created_at: '2026-08-31T10:00:00Z',
        })
        .mockResolvedValue({
          revision_id: 42,
          renderer: 'checkin-card',
          schema_version: 1,
          theme: { ...DEFAULT_COMMUNITY_OVERLAY_THEME, placement: 'top-left' },
          created_at: '2026-08-31T10:05:00Z',
        })
      vi.mocked(getCommunityOverlayFeed).mockResolvedValue({ cursor: 20, events: [] })

      renderOverlay(`#key=${KEY}`)
      await act(async () => Promise.resolve())
      await act(async () => {
        await vi.advanceTimersByTimeAsync(5_000)
      })

      expect(getCommunityOverlayTheme).toHaveBeenCalledTimes(4)
      expect(getCommunityOverlayTheme).toHaveBeenCalledWith(KEY, 'checkin')
      expect(getCommunityOverlayTheme).toHaveBeenCalledWith(KEY, 'tarot')
      expect(document.querySelector('main')).toHaveAttribute('data-placement', 'top-left')
    } finally {
      vi.useRealTimers()
    }
  })

  it('drops old tenant state and ignores an in-flight response after key changes', async () => {
    const oldFeed = deferred<{ cursor: number; events: ReturnType<typeof event>[] }>()
    vi.mocked(getCommunityOverlayFeed).mockImplementation(async key => {
      if (key === KEY) return oldFeed.promise
      return { cursor: 22, events: [event(22, 4, 'Bob')] }
    })

    render(
      <MemoryRouter initialEntries={[`/live-display#key=${KEY}&preview=1`]}>
        <SwitchingOverlay />
      </MemoryRouter>
    )

    fireEvent.click(screen.getByRole('button', { name: '切換租戶' }))
    expect(await screen.findByLabelText('Bob 的簽到集點卡')).toBeInTheDocument()

    oldFeed.resolve({ cursor: 21, events: [event(21, 3, 'Alice')] })
    await act(async () => Promise.resolve())

    expect(screen.queryByLabelText('Alice 的簽到集點卡')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Bob 的簽到集點卡')).toBeInTheDocument()
  })
})
