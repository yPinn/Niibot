import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { advanceVideoQueue } from '@/api/videoQueue'
import { openVideoQueueStream } from '@/api/videoQueueStream'

import VideoQueueOverlay from './VideoQueueOverlay'

vi.mock('@/api/videoQueue', () => ({
  advanceVideoQueue: vi.fn(),
  reportVideoMetadata: vi.fn(),
}))
vi.mock('@/api/videoQueueStream', () => ({ openVideoQueueStream: vi.fn() }))

const USERNAME = 'teststreamer'

function renderOverlay() {
  return render(
    <MemoryRouter initialEntries={[`/${USERNAME}/video-queue/overlay`]}>
      <Routes>
        <Route path="/:username/video-queue/overlay" element={<VideoQueueOverlay />} />
      </Routes>
    </MemoryRouter>
  )
}

// Bilibili is the only video type with no external player-API readiness gate
// (YouTube/Twitch require ytReady/twitchReady, which never resolve in jsdom),
// so it is the cheapest path to reach the "already ended" fast branch that
// calls handleVideoEnd without needing any player mocking.
function bilibiliEntry(id: number, requestedBy: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    video_id: `bv${id}`,
    title: `Video ${id}`,
    duration_seconds: 200,
    is_vertical: false,
    requested_by: requestedBy,
    source: 'chat',
    video_type: 'bilibili' as const,
    started_at: null,
    ...overrides,
  }
}

function youtubeEntry(id: number, requestedBy: string, overrides: Record<string, unknown> = {}) {
  return {
    ...bilibiliEntry(id, requestedBy, overrides),
    video_id: `yt${id}`,
    video_type: 'youtube' as const,
    ...overrides,
  }
}

describe('VideoQueueOverlay stream renderer', () => {
  beforeEach(() => {
    vi.mocked(openVideoQueueStream).mockReset()
    vi.mocked(openVideoQueueStream).mockImplementation(() => new Promise(() => undefined))
    vi.mocked(advanceVideoQueue).mockReset()
  })

  it('does not create periodic API requests while a stream remains open', async () => {
    vi.useFakeTimers()
    try {
      renderOverlay()
      await act(async () => vi.advanceTimersByTimeAsync(120_000))
      expect(openVideoQueueStream).toHaveBeenCalledTimes(1)
      expect(openVideoQueueStream).toHaveBeenCalledWith(
        expect.objectContaining({ username: USERNAME })
      )
    } finally {
      vi.useRealTimers()
    }
  })

  it('reconnects with exponential backoff when short streams disconnect immediately', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
    try {
      vi.mocked(openVideoQueueStream).mockImplementation(async () => undefined)
      renderOverlay()
      await act(async () => Promise.resolve())

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openVideoQueueStream).toHaveBeenCalledTimes(2)

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openVideoQueueStream).toHaveBeenCalledTimes(2)

      await act(async () => vi.advanceTimersByTimeAsync(1_000))
      expect(openVideoQueueStream).toHaveBeenCalledTimes(3)
    } finally {
      vi.mocked(Math.random).mockRestore()
      vi.useRealTimers()
    }
  })

  it('rejects a stale stream frame that still shows an already-advanced video as current', async () => {
    vi.useFakeTimers()
    try {
      // started 100s ago with a 1s duration puts joinElapsed past the
      // duration, so the "already ended" branch fires synchronously.
      const finishedEntry = bilibiliEntry(1, 'viewer-finished', {
        duration_seconds: 1,
        started_at: new Date(Date.now() - 100_000).toISOString(),
      })
      const nextEntry = bilibiliEntry(2, 'viewer-next')
      vi.mocked(advanceVideoQueue).mockResolvedValue({
        enabled: true,
        current: nextEntry,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })

      renderOverlay()
      const options = vi.mocked(openVideoQueueStream).mock.calls[0][0]
      act(() => {
        options.onMessage({
          type: 'snapshot',
          current: finishedEntry,
          queue: [],
          queue_size: 0,
          total_queued_duration: null,
        })
      })

      // handleVideoEnd's exit-animation delay, then the mocked advance POST settling.
      await act(async () => vi.advanceTimersByTimeAsync(600))
      await act(async () => Promise.resolve())
      expect(advanceVideoQueue).toHaveBeenCalledWith(USERNAME, 1)
      expect(screen.getByText('@ viewer-next')).toBeInTheDocument()

      // A frame that was already in flight before the advance committed
      // arrives late, still showing the finished video as current.
      act(() => {
        options.onMessage({
          type: 'update',
          current: finishedEntry,
          queue: [],
          queue_size: 0,
          total_queued_duration: null,
        })
      })

      expect(screen.getByText('@ viewer-next')).toBeInTheDocument()
      expect(screen.queryByText('@ viewer-finished')).not.toBeInTheDocument()
    } finally {
      vi.useRealTimers()
    }
  })
})

// The players/ package (see backend equivalent: resolve_video_url) selects a
// mount strategy per video_type. These two cases are the cheapest way to
// prove dispatch actually differs by platform: Bilibili's strategy declares
// no requiresApi and must mount synchronously; YouTube's declares
// requiresApi: 'youtube' and must stay gated forever in jsdom, where the real
// IFrame API script never loads and ytReady never becomes true.
describe('VideoQueueOverlay player strategy selection', () => {
  beforeEach(() => {
    vi.mocked(openVideoQueueStream).mockReset()
    vi.mocked(openVideoQueueStream).mockImplementation(() => new Promise(() => undefined))
  })

  it('mounts the Bilibili iframe immediately since its strategy needs no external API', () => {
    const entry = bilibiliEntry(1, 'viewer')
    const { container } = renderOverlay()
    const options = vi.mocked(openVideoQueueStream).mock.calls[0][0]
    act(() => {
      options.onMessage({
        type: 'snapshot',
        current: entry,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })
    })

    const iframe = container.querySelector('iframe')
    expect(iframe).not.toBeNull()
    expect(iframe?.getAttribute('src')).toContain(`bvid=${entry.video_id}`)
  })

  it('never mounts a YouTube video while ytReady is false (its strategy requires the IFrame API)', () => {
    const entry = youtubeEntry(1, 'viewer')
    const { container } = renderOverlay()
    const options = vi.mocked(openVideoQueueStream).mock.calls[0][0]
    act(() => {
      options.onMessage({
        type: 'snapshot',
        current: entry,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })
    })

    // jsdom never executes the injected `youtube.com/iframe_api` script, so
    // ytReady never flips true and the effect must bail out before touching
    // window.YT (which is undefined here) or writing into the container.
    expect(container.querySelector('iframe')).toBeNull()
    expect(container.querySelector(`[id^="twitch-embed-"]`)).toBeNull()
  })
})
