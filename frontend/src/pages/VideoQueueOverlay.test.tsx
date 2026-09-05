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
