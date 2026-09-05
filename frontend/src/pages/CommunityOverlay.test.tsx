import { MemoryRouter, useNavigate } from 'react-router-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { DEFAULT_COMMUNITY_OVERLAY_THEME } from '@/api/communityOverlay'
import { openCommunityOverlayStream } from '@/api/communityOverlayStream'

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
    occurred_at: '2026-08-31T10:00:00Z',
    expires_at: '2026-08-31T10:10:00Z',
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
