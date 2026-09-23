import { MemoryRouter, useNavigate } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { frameSteps, MotionGlobalConfig } from 'motion/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
} from '@/api/communityOverlay'
import { openCommunityOverlayStream } from '@/api/communityOverlayStream'

import CommunityOverlay from './CommunityOverlay'

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
}))
vi.mock('@/api/communityOverlayStream', () => ({ openCommunityOverlayStream: vi.fn() }))

const KEY = '11111111-1111-4111-8111-111111111111'
const SECOND_KEY = '22222222-2222-4222-8222-222222222222'

function event(id: number, totalDays = 8, actor = 'Alice') {
  return {
    id,
    event_type: 'checkin.recorded' as const,
    schema_version: 1,
    source: 'twitch',
    actor_display_name: actor,
    payload: { total_days: totalDays, checkin_date: '2026-08-31' },
    occurred_at: '2099-08-31T10:00:00Z',
    expires_at: '2099-08-31T10:10:00Z',
  }
}

function collectionEvent(id: number, actor = 'Alice') {
  return {
    ...event(id, 8, actor),
    payload: {
      total_days: 8,
      checkin_date: '2099-08-31',
      collection: {
        draw_id: id + 100,
        pool_revision_id: 3,
        algorithm_version: 'weighted-rarity-v1',
        card: {
          id: id + 200,
          revision_id: 2,
          key: `card-${id}`,
          number: `GI-${id}`,
          name: `收藏卡 ${id}`,
          artwork: {
            portrait_url: `/images/collections/card-${id}.webp`,
            square_url: null,
            backdrop_url: null,
          },
        },
        set: { id: 1, key: 'starter-isles', name: '浮游群島' },
        rarity: { key: 'rare', label: '稀有', rank: 2, effect_intensity: 50 },
        is_new: true,
        copy_count: 1,
        progress: { owned_copies: 8, unique_cards: 6, total_cards: 24 },
      },
    },
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
      orientation: 'upright' as const,
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
    occurred_at: '2099-08-31T10:00:00Z',
    expires_at: '2099-08-31T10:10:00Z',
  }
}

const checkinTheme = (
  revisionId: number,
  placement: 'bottom-left' | 'top-left' = 'bottom-left'
) => ({
  revision_id: revisionId,
  renderer: 'checkin-card',
  schema_version: 1,
  theme: { ...DEFAULT_COMMUNITY_OVERLAY_THEME, placement },
  created_at: '2026-08-31T10:00:00Z',
})

const tarotTheme = (revisionId: number) => ({
  revision_id: revisionId,
  renderer: 'tarot-card',
  schema_version: 1,
  theme: {
    ...DEFAULT_TAROT_OVERLAY_THEME,
    placement: 'top-left' as const,
    display_ms: 2_000,
  },
  created_at: '2026-08-31T10:00:00Z',
})

function renderOverlay(hash: string) {
  return render(
    <MemoryRouter initialEntries={[`/live-display${hash}`]}>
      <CommunityOverlay />
    </MemoryRouter>
  )
}

function SwitchingOverlay() {
  const navigate = useNavigate()
  return (
    <>
      <button type="button" onClick={() => navigate(`/live-display#key=${SECOND_KEY}&preview=1`)}>
        切換租戶
      </button>
      <CommunityOverlay />
    </>
  )
}

describe('CommunityOverlay stream renderer', () => {
  beforeEach(() => {
    vi.mocked(openCommunityOverlayStream).mockReset()
    vi.mocked(openCommunityOverlayStream).mockImplementation(() => new Promise(() => undefined))
  })

  it('stays transparent and opens no transport without a capability key', () => {
    renderOverlay('')
    expect(openCommunityOverlayStream).not.toHaveBeenCalled()
    expect(document.querySelector('[data-overlay-card]')).not.toBeInTheDocument()
  })

  it('uses no-replay for live and cursor zero only for explicit preview', () => {
    renderOverlay(`#key=${KEY}`)
    expect(openCommunityOverlayStream).toHaveBeenCalledWith(
      expect.objectContaining({ publicKey: KEY, afterId: undefined })
    )
    renderOverlay(`#key=${SECOND_KEY}&preview=1`)
    expect(openCommunityOverlayStream).toHaveBeenLastCalledWith(
      expect.objectContaining({ publicKey: SECOND_KEY, afterId: 0 })
    )
  })

  it('plays the development check-in sample through the binder without opening a stream', () => {
    renderOverlay(`#key=${KEY}&preview=1&block=checkin&sample=checkin`)

    expect(screen.getByLabelText('NiibotFan 的卡冊：獲得普通卡Karina')).toBeInTheDocument()
    expect(screen.getByTestId('collection-binder')).toHaveAttribute(
      'data-animation-sequence',
      'closed open card insert close'
    )
    expect(openCommunityOverlayStream).not.toHaveBeenCalled()
  })

  it('applies snapshot theme and renders ordered valid events', async () => {
    renderOverlay(`#key=${KEY}&preview=1`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() =>
      options.onMessage({
        type: 'snapshot',
        cursor: 22,
        events: [event(21), tarotEvent(22)],
        themes: { checkin: checkinTheme(42, 'top-left') },
      })
    )
    const card = await screen.findByLabelText('Alice 的簽到集點卡')
    expect(card.closest('main')).toHaveAttribute('data-placement', 'top-left')
    expect(card).toHaveStyle({ '--overlay-radius': '24px' })
  })

  it('ignores an unknown theme key without dropping valid events from the same frame', async () => {
    renderOverlay(`#key=${KEY}&preview=1`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() =>
      options.onMessage({
        type: 'snapshot',
        cursor: 23,
        events: [event(23)],
        themes: { future_block: checkinTheme(43) } as never,
      })
    )

    expect(await screen.findByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
  })

  it('filters out other block types when a block filter is present in the URL', async () => {
    renderOverlay(`#key=${KEY}&preview=1&block=checkin`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() =>
      options.onMessage({
        type: 'snapshot',
        cursor: 30,
        events: [tarotEvent(29), event(30)],
        themes: {},
      })
    )
    expect(await screen.findByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
    expect(screen.queryByLabelText(/Alice 的每日塔羅/)).not.toBeInTheDocument()
  })

  it('ignores an unrecognized block filter value and shows every content type', async () => {
    renderOverlay(`#key=${KEY}&preview=1&block=unknown`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() =>
      options.onMessage({
        type: 'snapshot',
        cursor: 30,
        events: [tarotEvent(29), event(30)],
        themes: {},
      })
    )
    expect(await screen.findByLabelText(/Alice 的每日塔羅/)).toBeInTheDocument()
  })

  it('deduplicates replayed IDs and ignores unsupported event versions', async () => {
    renderOverlay(`#key=${KEY}&preview=1`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() => {
      options.onMessage({
        type: 'snapshot',
        cursor: 30,
        events: [{ ...event(29), schema_version: 2 }, event(30)],
        themes: {},
      })
      options.onMessage({ type: 'update', cursor: 30, events: [event(30)], themes: {} })
    })
    expect(await screen.findByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
    expect(screen.getAllByLabelText('Alice 的簽到集點卡')).toHaveLength(1)
  })

  it('renders a validated collection snapshot with the binder and falls back on malformed data', async () => {
    const first = renderOverlay(`#key=${KEY}&preview=1`)
    const firstOptions = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() =>
      firstOptions.onMessage({
        type: 'snapshot',
        cursor: 31,
        events: [
          {
            ...collectionEvent(31),
            payload: { ...collectionEvent(31).payload, collection: null },
          },
        ],
        themes: {},
      })
    )
    expect(screen.getByLabelText('Alice 的簽到集點卡')).toBeInTheDocument()
    first.unmount()

    renderOverlay(`#key=${SECOND_KEY}&preview=1`)
    const secondOptions = vi.mocked(openCommunityOverlayStream).mock.calls[1][0]
    act(() =>
      secondOptions.onMessage({
        type: 'snapshot',
        cursor: 32,
        events: [collectionEvent(32, 'Bob')],
        themes: {},
      })
    )
    expect(screen.getByLabelText('Bob 的卡冊：獲得稀有卡收藏卡 32')).toBeInTheDocument()
  })

  it('drops expired events at ingest and rechecks queued events before promotion', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-09-08T10:00:00Z'))
    try {
      renderOverlay(`#key=${KEY}&preview=1`)
      const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
      const expiresWhileQueued = {
        ...collectionEvent(42, 'Queued'),
        expires_at: '2026-09-08T10:00:03Z',
      }
      act(() =>
        options.onMessage({
          type: 'snapshot',
          cursor: 43,
          events: [
            { ...event(40, 2, 'Already expired'), expires_at: '2026-09-08T09:59:59Z' },
            { ...event(44, 2, 'Invalid expiry'), expires_at: 'not-a-date' },
            { ...collectionEvent(41, 'Active'), expires_at: '2026-09-08T10:01:00Z' },
            expiresWhileQueued,
            { ...event(43, 3, 'Fresh'), expires_at: '2026-09-08T10:01:00Z' },
          ],
          themes: {},
        })
      )

      expect(screen.getByLabelText('Active 的卡冊：獲得稀有卡收藏卡 41')).toBeInTheDocument()
      expect(screen.queryByLabelText('Already expired 的簽到集點卡')).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Invalid expiry 的簽到集點卡')).not.toBeInTheDocument()

      await act(async () => vi.advanceTimersByTimeAsync(5_100))
      expect(screen.getByLabelText('Fresh 的簽到集點卡')).toBeInTheDocument()
      expect(screen.queryByLabelText(/Queued 的卡冊/)).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps a short configured collection reveal mounted through its five-second ritual', async () => {
    vi.useFakeTimers()
    try {
      renderOverlay(`#key=${KEY}&preview=1`)
      const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
      const shortTheme = checkinTheme(50)
      shortTheme.theme = { ...shortTheme.theme, display_ms: 2_000 }

      act(() =>
        options.onMessage({
          type: 'snapshot',
          cursor: 61,
          events: [collectionEvent(60, 'Binder'), event(61, 2, 'Legacy')],
          themes: { checkin: shortTheme },
        })
      )

      expect(screen.getByLabelText(/Binder 的卡冊/)).toBeInTheDocument()
      await act(async () => vi.advanceTimersByTimeAsync(5_000))
      expect(screen.getByLabelText(/Binder 的卡冊/)).toBeInTheDocument()

      await act(async () => vi.advanceTimersByTimeAsync(100))
      expect(screen.getByLabelText('Legacy 的簽到集點卡')).toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('does not start the next binder timer or move placement while tarot is exiting', async () => {
    vi.useFakeTimers()
    MotionGlobalConfig.useManualTiming = true
    const timeoutSpy = vi.spyOn(window, 'setTimeout')
    try {
      renderOverlay(`#key=${KEY}&preview=1`)
      const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
      act(() =>
        options.onMessage({
          type: 'snapshot',
          cursor: 72,
          events: [
            tarotEvent(70, 'Tarot viewer'),
            collectionEvent(71, 'Binder viewer'),
            event(72, 9, 'Next viewer'),
          ],
          themes: { tarot: tarotTheme(70) },
        })
      )

      const tarot = screen.getByLabelText(/Tarot viewer 的每日塔羅/)
      expect(tarot.closest('main')).toHaveAttribute('data-placement', 'top-left')
      expect(timeoutSpy.mock.calls.some(([, delay]) => delay === 5_100)).toBe(false)

      await act(async () => vi.advanceTimersByTimeAsync(2_000))
      expect(screen.getByLabelText(/Tarot viewer 的每日塔羅/)).toBeInTheDocument()
      expect(screen.queryByLabelText(/Binder viewer 的卡冊/)).not.toBeInTheDocument()
      expect(tarot.closest('main')).toHaveAttribute('data-placement', 'top-left')
      expect(timeoutSpy.mock.calls.some(([, delay]) => delay === 5_100)).toBe(false)

      for (
        let tick = 1;
        tick <= 50 && !screen.queryByLabelText(/Binder viewer 的卡冊/);
        tick += 1
      ) {
        const frame = { delta: 16, timestamp: 2_000 + tick * 16, isProcessing: true }
        await act(async () => {
          frameSteps.setup.process(frame)
          frameSteps.read.process(frame)
          frameSteps.resolveKeyframes.process(frame)
          frameSteps.preUpdate.process(frame)
          frameSteps.update.process(frame)
          frameSteps.preRender.process(frame)
          frameSteps.render.process(frame)
          frameSteps.postRender.process(frame)
          await Promise.resolve()
        })
      }
      expect(screen.getByLabelText(/Binder viewer 的卡冊/)).toBeInTheDocument()
      expect(timeoutSpy.mock.calls.some(([, delay]) => delay === 5_100)).toBe(true)

      await act(async () => vi.advanceTimersByTimeAsync(5_000))
      expect(screen.getByLabelText(/Binder viewer 的卡冊/)).toBeInTheDocument()

      await act(async () => vi.advanceTimersByTimeAsync(100))
      expect(screen.getByLabelText('Next viewer 的簽到集點卡')).toBeInTheDocument()
    } finally {
      timeoutSpy.mockRestore()
      MotionGlobalConfig.useManualTiming = false
      vi.useRealTimers()
    }
  })

  it('freezes the resolved theme for the active event and applies a newer revision next', async () => {
    vi.useFakeTimers()
    try {
      renderOverlay(`#key=${KEY}&preview=1`)
      const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
      const oldTheme = checkinTheme(41, 'bottom-left')
      oldTheme.theme = { ...oldTheme.theme, display_ms: 5_000, accent_color: '#112233' }
      const newTheme = checkinTheme(42, 'top-left')
      newTheme.theme = { ...newTheme.theme, display_ms: 8_000, accent_color: '#445566' }

      act(() =>
        options.onMessage({
          type: 'snapshot',
          cursor: 51,
          events: [collectionEvent(51, 'Alice')],
          themes: { checkin: oldTheme },
        })
      )
      expect(screen.getByLabelText(/Alice 的卡冊/).closest('main')).toHaveAttribute(
        'data-placement',
        'bottom-left'
      )
      expect(screen.getByLabelText(/Alice 的卡冊/)).toHaveStyle({
        '--overlay-accent': '#112233',
      })

      act(() =>
        options.onMessage({
          type: 'update',
          cursor: 52,
          events: [collectionEvent(52, 'Bob')],
          themes: { checkin: newTheme },
        })
      )
      expect(screen.getByLabelText(/Alice 的卡冊/).closest('main')).toHaveAttribute(
        'data-placement',
        'bottom-left'
      )

      await act(async () => vi.advanceTimersByTimeAsync(5_100))
      expect(screen.getByLabelText(/Bob 的卡冊/).closest('main')).toHaveAttribute(
        'data-placement',
        'top-left'
      )
      expect(screen.getByLabelText(/Bob 的卡冊/)).toHaveStyle({
        '--overlay-accent': '#445566',
      })
      expect(screen.queryByLabelText(/Alice 的卡冊/)).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })

  it('hot-updates a published theme without remounting', () => {
    renderOverlay(`#key=${KEY}`)
    const options = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    act(() => {
      options.onMessage({
        type: 'snapshot',
        cursor: 1,
        events: [],
        themes: { checkin: checkinTheme(41) },
      })
      options.onMessage({
        type: 'update',
        cursor: 1,
        events: [],
        themes: { checkin: checkinTheme(42, 'top-left') },
      })
    })
    expect(document.querySelector('main')).toHaveAttribute('data-placement', 'top-left')
  })

  it('does not create periodic API requests while a stream remains open', async () => {
    vi.useFakeTimers()
    try {
      renderOverlay(`#key=${KEY}`)
      await act(async () => vi.advanceTimersByTimeAsync(120_000))
      expect(openCommunityOverlayStream).toHaveBeenCalledTimes(1)
    } finally {
      vi.useRealTimers()
    }
  })

  it('reconnects with the last cursor after disconnect', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    try {
      vi.mocked(openCommunityOverlayStream).mockImplementationOnce(async options => {
        options.onMessage({ type: 'snapshot', cursor: 10, events: [], themes: {} })
      })
      renderOverlay(`#key=${KEY}`)
      await act(async () => Promise.resolve())
      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openCommunityOverlayStream).toHaveBeenNthCalledWith(
        2,
        expect.objectContaining({ publicKey: KEY, afterId: 10 })
      )
    } finally {
      vi.mocked(Math.random).mockRestore()
      vi.useRealTimers()
    }
  })

  it('keeps exponential backoff when short streams send a snapshot then disconnect', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    try {
      vi.mocked(openCommunityOverlayStream).mockImplementation(async options => {
        options.onMessage({ type: 'snapshot', cursor: 10, events: [], themes: {} })
      })
      renderOverlay(`#key=${KEY}`)
      await act(async () => Promise.resolve())

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openCommunityOverlayStream).toHaveBeenCalledTimes(2)

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openCommunityOverlayStream).toHaveBeenCalledTimes(2)

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openCommunityOverlayStream).toHaveBeenCalledTimes(3)
    } finally {
      vi.mocked(Math.random).mockRestore()
      vi.useRealTimers()
    }
  })

  it('aborts the old tenant stream and ignores its late frame after key changes', async () => {
    render(
      <MemoryRouter initialEntries={[`/live-display#key=${KEY}&preview=1`]}>
        <SwitchingOverlay />
      </MemoryRouter>
    )
    const oldOptions = vi.mocked(openCommunityOverlayStream).mock.calls[0][0]
    fireEvent.click(screen.getByRole('button', { name: '切換租戶' }))
    await waitFor(() => expect(openCommunityOverlayStream).toHaveBeenCalledTimes(2))
    expect(oldOptions.signal.aborted).toBe(true)
    const nextOptions = vi.mocked(openCommunityOverlayStream).mock.calls[1][0]
    act(() => {
      oldOptions.onMessage({ type: 'update', cursor: 21, events: [event(21)], themes: {} })
      nextOptions.onMessage({
        type: 'snapshot',
        cursor: 22,
        events: [event(22, 4, 'Bob')],
        themes: {},
      })
    })
    expect(await screen.findByLabelText('Bob 的簽到集點卡')).toBeInTheDocument()
    expect(screen.queryByLabelText('Alice 的簽到集點卡')).not.toBeInTheDocument()
  })
})
