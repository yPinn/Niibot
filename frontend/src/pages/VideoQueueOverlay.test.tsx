import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { act, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  advanceVideoQueue,
  fetchTwitchClipSource,
  getPublicVideoQueueState,
  reportPlaybackStarted,
} from '@/api/videoQueue'
import { openVideoQueueStream } from '@/api/videoQueueStream'

import VideoQueueOverlay from './VideoQueueOverlay'

vi.mock('@/api/videoQueue', () => ({
  advanceVideoQueue: vi.fn(),
  reportPlaybackStarted: vi.fn().mockResolvedValue(undefined),
  reportVideoMetadata: vi.fn(),
  fetchTwitchClipSource: vi.fn().mockResolvedValue(null),
  getPublicVideoQueueState: vi.fn(),
}))
vi.mock('@/api/videoQueueStream', () => ({ openVideoQueueStream: vi.fn() }))

const USERNAME = 'teststreamer'
const OVERLAY_KEY = '11111111-1111-4111-8111-111111111111'

function renderOverlay(location = `#key=${OVERLAY_KEY}`) {
  return render(
    <MemoryRouter initialEntries={[`/${USERNAME}/video-queue/overlay${location}`]}>
      <Routes>
        <Route path="/:username/video-queue/overlay" element={<VideoQueueOverlay />} />
      </Routes>
    </MemoryRouter>
  )
}

// Bilibili and Twitch clips are plain iframes with no external player-API
// readiness gate (only YouTube requires ytReady, which never resolves in jsdom),
// so they are the cheapest path to reach the "already ended" fast branch that
// calls handleVideoEnd without needing any player mocking.
function bilibiliEntry(id: number, requestedBy: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    video_id: `bv${id}`,
    title: `Video ${id}`,
    duration_seconds: 200,
    is_vertical: false,
    start_seconds: 0,
    requested_by: requestedBy,
    source: 'chat',
    video_type: 'bilibili' as const,
    started_at: null,
    ...overrides,
  }
}

function twitchVodEntry(id: number, requestedBy: string, overrides: Record<string, unknown> = {}) {
  return {
    ...bilibiliEntry(id, requestedBy, overrides),
    video_id: `${id}`,
    video_type: 'twitch_vod' as const,
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

function twitchClipEntry(id: number, requestedBy: string, overrides: Record<string, unknown> = {}) {
  return {
    ...bilibiliEntry(id, requestedBy, overrides),
    video_id: `clip${id}`,
    video_type: 'twitch_clip' as const,
    ...overrides,
  }
}

describe('VideoQueueOverlay stream renderer', () => {
  beforeEach(() => {
    vi.mocked(openVideoQueueStream).mockReset()
    vi.mocked(openVideoQueueStream).mockImplementation(() => new Promise(() => undefined))
    vi.mocked(advanceVideoQueue).mockReset()
    vi.mocked(reportPlaybackStarted).mockReset()
    vi.mocked(reportPlaybackStarted).mockResolvedValue(undefined)
    vi.mocked(getPublicVideoQueueState).mockResolvedValue({
      enabled: true,
      volume_percent: 100,
      current: null,
      queue: [],
      queue_size: 0,
      total_queued_duration: null,
    })
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
        volume_percent: 100,
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
      expect(advanceVideoQueue).toHaveBeenCalledWith(USERNAME, 1, OVERLAY_KEY)
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

  it('retries a transiently failed advance without accepting stale stream state', async () => {
    vi.useFakeTimers()
    try {
      const finishedEntry = bilibiliEntry(9, 'viewer-finished', {
        duration_seconds: 1,
        started_at: new Date(Date.now() - 100_000).toISOString(),
      })
      vi.mocked(advanceVideoQueue)
        .mockRejectedValueOnce(new Error('temporary network failure'))
        .mockResolvedValueOnce({
          enabled: true,
          volume_percent: 100,
          current: null,
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

      await act(async () => vi.advanceTimersByTimeAsync(600))
      expect(advanceVideoQueue).toHaveBeenCalledTimes(1)

      act(() => {
        options.onMessage({
          type: 'update',
          current: finishedEntry,
          queue: [],
          queue_size: 0,
          total_queued_duration: null,
        })
      })
      await act(async () => vi.advanceTimersByTimeAsync(2_000))

      expect(advanceVideoQueue).toHaveBeenCalledTimes(2)
      expect(advanceVideoQueue).toHaveBeenLastCalledWith(USERNAME, 9, OVERLAY_KEY)
    } finally {
      vi.useRealTimers()
    }
  })

  it('retries a transiently failed idle kickstart while the queue is unchanged', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(advanceVideoQueue)
        .mockRejectedValueOnce(new Error('temporary network failure'))
        .mockResolvedValueOnce({
          enabled: true,
          volume_percent: 100,
          current: bilibiliEntry(10, 'viewer'),
          queue: [],
          queue_size: 0,
          total_queued_duration: null,
        })

      renderOverlay()
      const options = vi.mocked(openVideoQueueStream).mock.calls[0][0]
      act(() => {
        options.onMessage({
          type: 'snapshot',
          current: null,
          queue: [bilibiliEntry(10, 'viewer')],
          queue_size: 1,
          total_queued_duration: 200,
        })
      })
      await act(async () => Promise.resolve())
      expect(advanceVideoQueue).toHaveBeenCalledTimes(1)

      await act(async () => vi.advanceTimersByTimeAsync(2_000))

      expect(advanceVideoQueue).toHaveBeenCalledTimes(2)
      expect(advanceVideoQueue).toHaveBeenLastCalledWith(USERNAME, null, OVERLAY_KEY)
    } finally {
      vi.useRealTimers()
    }
  })
})

// The players/ package (see backend equivalent: resolve_video_url) selects a
// mount strategy per video_type. These cases prove dispatch actually differs by
// platform: Bilibili and Twitch clips declare no requiresApi and must mount
// synchronously; YouTube declares requiresApi: 'youtube' and must stay gated
// forever in jsdom, where the real IFrame API script never loads and ytReady
// never becomes true.
describe('VideoQueueOverlay player strategy selection', () => {
  beforeEach(() => {
    vi.mocked(openVideoQueueStream).mockReset()
    vi.mocked(openVideoQueueStream).mockImplementation(() => new Promise(() => undefined))
    vi.mocked(advanceVideoQueue).mockReset()
    vi.mocked(getPublicVideoQueueState).mockResolvedValue({
      enabled: true,
      volume_percent: 100,
      current: null,
      queue: [],
      queue_size: 0,
      total_queued_duration: null,
    })
  })

  function pushCurrent(entry: ReturnType<typeof bilibiliEntry>) {
    const options = vi.mocked(openVideoQueueStream).mock.calls.at(-1)![0]
    act(() => {
      options.onMessage({
        type: 'snapshot',
        current: entry,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })
    })
  }

  // The Twitch clip strategy resolves its signed source URL before mounting;
  // flush that microtask so the <video> / fallback iframe is in the DOM.
  const flush = () => act(async () => undefined)

  it('mounts the Bilibili iframe immediately since its strategy needs no external API', () => {
    const entry = bilibiliEntry(1, 'viewer')
    const { container } = renderOverlay()
    pushCurrent(entry)

    const iframe = container.querySelector('iframe')
    expect(iframe).not.toBeNull()
    const src = iframe?.getAttribute('src') ?? ''
    expect(src).toContain('player.bilibili.com/player.html')
    expect(src).toContain(`bvid=${entry.video_id}`)
    // OBS overlay (not ?preview=1): no `muted` param — it plays with sound.
    expect(src).not.toContain('muted=')
    expect(document.head.querySelector('script[src*="youtube.com/iframe_api"]')).toBeNull()
    expect(document.head.querySelector('script[src*="player.twitch.tv/js/embed"]')).toBeNull()
  })

  it('plays a Twitch clip in a <video> when the signed source resolves', async () => {
    vi.mocked(fetchTwitchClipSource).mockResolvedValueOnce('https://cdn.twitchcdn.net/c.mp4?sig=a')
    const { container } = renderOverlay()
    pushCurrent(twitchClipEntry(1, 'viewer'))
    await flush()

    const video = container.querySelector('video')
    expect(video).not.toBeNull()
    expect(video?.getAttribute('src')).toBe('https://cdn.twitchcdn.net/c.mp4?sig=a')
    expect(container.querySelector('iframe')).toBeNull()
    expect(fetchTwitchClipSource).toHaveBeenCalledWith(USERNAME, 1)
  })

  it('applies the configured normalized volume to a host-controlled video', async () => {
    vi.mocked(getPublicVideoQueueState).mockResolvedValueOnce({
      enabled: true,
      volume_percent: 35,
      current: null,
      queue: [],
      queue_size: 0,
      total_queued_duration: null,
    })
    vi.mocked(fetchTwitchClipSource).mockResolvedValueOnce('https://cdn.twitchcdn.net/c.mp4?sig=a')
    const { container } = renderOverlay()
    await flush()
    pushCurrent(twitchClipEntry(1, 'viewer'))
    await flush()

    expect(container.querySelector('video')?.volume).toBe(0.35)
  })

  it('falls back to the clips.twitch.tv/embed iframe when no signed source is available', async () => {
    vi.mocked(fetchTwitchClipSource).mockResolvedValueOnce(null)
    const entry = twitchClipEntry(1, 'viewer')
    const { container } = renderOverlay()
    pushCurrent(entry)
    await flush()

    const iframe = container.querySelector('iframe')
    expect(iframe).not.toBeNull()
    const src = iframe?.getAttribute('src') ?? ''
    expect(src).toContain('https://clips.twitch.tv/embed?')
    expect(src).toContain(`clip=${entry.video_id}`)
    expect(src).toContain('autoplay=true')
    expect(src).toContain('muted=false')
  })

  it('labels iframe load as best-effort playback and keeps preview read-only', async () => {
    vi.mocked(fetchTwitchClipSource).mockResolvedValue(null)
    const { container, unmount } = renderOverlay()
    pushCurrent(twitchClipEntry(6, 'viewer'))
    await flush()
    act(() => container.querySelector('iframe')?.dispatchEvent(new Event('load')))

    expect(reportPlaybackStarted).toHaveBeenCalledWith(USERNAME, 6, 'best_effort', OVERLAY_KEY)

    unmount()
    vi.mocked(reportPlaybackStarted).mockClear()
    const preview = renderOverlay(`?preview=1#key=${OVERLAY_KEY}`)
    pushCurrent(twitchClipEntry(7, 'viewer'))
    await flush()
    act(() => preview.container.querySelector('iframe')?.dispatchEvent(new Event('load')))
    expect(reportPlaybackStarted).not.toHaveBeenCalled()
  })

  it('mutes the fallback clip iframe / bilibili iframe in the dashboard preview (?preview=1)', async () => {
    vi.mocked(fetchTwitchClipSource).mockResolvedValueOnce(null)
    const { container } = renderOverlay(`?preview=1#key=${OVERLAY_KEY}`)
    pushCurrent(twitchClipEntry(1, 'viewer'))
    await flush()
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('muted=true')
  })

  it('mutes the Bilibili preview with an explicit muted=1 param', () => {
    const { container } = renderOverlay(`?preview=1#key=${OVERLAY_KEY}`)
    pushCurrent(bilibiliEntry(1, 'viewer'))
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('muted=1')
  })

  it('follows authoritative current-item stream changes without mutating the queue', () => {
    const { container } = renderOverlay(`?preview=1#key=${OVERLAY_KEY}`)
    const options = vi.mocked(openVideoQueueStream).mock.calls.at(-1)![0]

    act(() => {
      options.onMessage({
        type: 'snapshot',
        current: bilibiliEntry(1, 'first-viewer'),
        queue: [bilibiliEntry(2, 'second-viewer')],
        queue_size: 1,
        total_queued_duration: 200,
      })
    })
    expect(screen.getByText('@ first-viewer')).toBeInTheDocument()
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('bvid=bv1')

    act(() => {
      options.onMessage({
        type: 'update',
        current: bilibiliEntry(2, 'second-viewer'),
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })
    })
    expect(screen.getByText('@ second-viewer')).toBeInTheDocument()
    expect(container.querySelector('iframe')?.getAttribute('src')).toContain('bvid=bv2')
    expect(advanceVideoQueue).not.toHaveBeenCalled()
    expect(reportPlaybackStarted).not.toHaveBeenCalled()
  })

  it('never mounts a YouTube video while ytReady is false (its strategy requires the IFrame API)', () => {
    const entry = youtubeEntry(1, 'viewer')
    const { container } = renderOverlay()
    pushCurrent(entry)

    // jsdom never executes the injected `youtube.com/iframe_api` script, so
    // ytReady never flips true and the effect must bail out before touching
    // window.YT (which is undefined here) or writing into the container.
    expect(container.querySelector('iframe')).toBeNull()
  })

  it('advances when an external player API never becomes ready', async () => {
    vi.useFakeTimers()
    try {
      vi.mocked(advanceVideoQueue).mockResolvedValue({
        enabled: true,
        volume_percent: 100,
        current: null,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })
      renderOverlay()
      pushCurrent(youtubeEntry(44, 'viewer'))

      await act(async () => vi.advanceTimersByTimeAsync(15_000 + 600))
      await act(async () => Promise.resolve())

      expect(advanceVideoQueue).toHaveBeenCalledWith(USERNAME, 44, OVERLAY_KEY, 'startup_timeout')
    } finally {
      vi.useRealTimers()
    }
  })

  it('never mounts a Twitch VOD while twitchReady is false (its strategy requires the embed API)', () => {
    const { container } = renderOverlay()
    pushCurrent(twitchVodEntry(1234, 'viewer'))
    // jsdom never runs the injected embed/v1.js, so window.Twitch stays
    // undefined and the effect must bail before `new Twitch.Player(...)`.
    expect(container.querySelector('iframe')).toBeNull()
    expect(container.querySelector('video')).toBeNull()
  })

  it('advances via the fallback ceiling when an entry has no duration', async () => {
    vi.useFakeTimers()
    try {
      const noDuration = twitchClipEntry(1, 'viewer', {
        duration_seconds: null,
        started_at: new Date().toISOString(),
      })
      vi.mocked(advanceVideoQueue).mockResolvedValue({
        enabled: true,
        volume_percent: 100,
        current: null,
        queue: [],
        queue_size: 0,
        total_queued_duration: null,
      })

      const { container } = renderOverlay()
      pushCurrent(noDuration)
      // Clip source resolves to null (default mock) → fallback iframe + timer.
      await act(async () => undefined)
      act(() => container.querySelector('iframe')?.dispatchEvent(new Event('load')))
      expect(advanceVideoQueue).not.toHaveBeenCalled()

      // CLIP_MAX_SECONDS (90s) + the exit-animation delay, then the POST settling.
      await act(async () => vi.advanceTimersByTimeAsync(91_000 + 600))
      await act(async () => Promise.resolve())
      expect(advanceVideoQueue).toHaveBeenCalledWith(USERNAME, 1, OVERLAY_KEY)
    } finally {
      vi.useRealTimers()
    }
  })

  it('keeps dashboard preview read-only when queued media has no current item', async () => {
    renderOverlay(`?preview=1#key=${OVERLAY_KEY}`)
    const options = vi.mocked(openVideoQueueStream).mock.calls[0][0]

    act(() => {
      options.onMessage({
        type: 'snapshot',
        current: null,
        queue: [bilibiliEntry(2, 'viewer')],
        queue_size: 1,
        total_queued_duration: 200,
      })
    })
    await act(async () => Promise.resolve())

    expect(advanceVideoQueue).not.toHaveBeenCalled()
  })
})
