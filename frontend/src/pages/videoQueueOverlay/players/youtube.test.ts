import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { reportVideoMetadata } from '@/api/videoQueue'

import type { MountContext, YTPlayer, YTPlayerOptions } from './types'
import { youtubeStrategy } from './youtube'

vi.mock('@/api/videoQueue', () => ({ reportVideoMetadata: vi.fn(() => Promise.resolve()) }))

function makePlayer(currentTime = 0, duration = 300) {
  return {
    playVideo: vi.fn(),
    pauseVideo: vi.fn(),
    destroy: vi.fn(),
    getCurrentTime: vi.fn(() => currentTime),
    getDuration: vi.fn(() => duration),
    seekTo: vi.fn(),
    setVolume: vi.fn(),
    mute: vi.fn(),
    unMute: vi.fn(),
  }
}

let options: YTPlayerOptions | undefined

function installYouTube(player: ReturnType<typeof makePlayer>) {
  options = undefined
  ;(window as unknown as { YT: unknown }).YT = {
    Player: vi.fn(function (_el: unknown, opts: YTPlayerOptions) {
      options = opts
      return player
    }),
  }
}

function ctx(overrides: Partial<MountContext['current']> = {}, joinElapsed = 0): MountContext {
  return {
    current: {
      id: 7,
      video_id: 'dQw4w9WgXcQ',
      title: 'A video',
      duration_seconds: 150,
      is_vertical: false,
      start_seconds: 90,
      requested_by: 'viewer',
      source: 'chat',
      video_type: 'youtube',
      started_at: null,
      ...overrides,
    },
    currentId: 7,
    joinElapsed,
    isPreview: false,
    overlayKey: '11111111-1111-4111-8111-111111111111',
    muted: false,
    volumePercent: 35,
    username: 'streamer',
    containerRef: { current: document.createElement('div') },
    leftContainerRef: { current: null },
    rightContainerRef: { current: null },
    playerRef: { current: null },
    leftPlayerRef: { current: null },
    rightPlayerRef: { current: null },
    progressRef: { current: null },
    clipTimerRef: { current: null },
    playbackStartTimerRef: { current: null },
    currentIdRef: { current: null },
    setElapsed: vi.fn(),
    notifyPlaybackStarted: vi.fn(),
    handleVideoEnd: vi.fn(),
  } as MountContext
}

function ready(player: ReturnType<typeof makePlayer>) {
  options?.events?.onReady?.({ target: player as unknown as YTPlayer })
}

describe('youtubeStrategy segments', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.mocked(reportVideoMetadata).mockClear()
  })

  it('cues the segment start', () => {
    installYouTube(makePlayer())
    youtubeStrategy.mount(ctx())
    expect(options?.playerVars?.start).toBe(90)
  })

  it('seeks a late-joining overlay to start + joinElapsed', () => {
    const player = makePlayer()
    installYouTube(player)
    youtubeStrategy.mount(ctx({}, 30))
    ready(player)
    expect(options?.playerVars?.start).toBe(120)
    expect(player.seekTo).toHaveBeenCalledWith(120, true)
  })

  it('ends at start + duration and reports elapsed relative to the start', () => {
    const player = makePlayer(100)
    installYouTube(player)
    const context = ctx()
    youtubeStrategy.mount(context)
    ready(player)

    vi.advanceTimersByTime(1000)
    expect(context.setElapsed).toHaveBeenLastCalledWith(10)
    expect(context.handleVideoEnd).not.toHaveBeenCalled()

    player.getCurrentTime.mockReturnValue(240)
    vi.advanceTimersByTime(1000)
    expect(context.handleVideoEnd).toHaveBeenCalledWith(7)
  })

  it('plays a whole video to its natural end when there is no segment', () => {
    const player = makePlayer(0, 300)
    installYouTube(player)
    const context = ctx({ start_seconds: 0, duration_seconds: 300 })
    youtubeStrategy.mount(context)
    ready(player)
    expect(options?.playerVars?.start).toBe(0)
    expect(player.seekTo).not.toHaveBeenCalled()

    player.getCurrentTime.mockReturnValue(299.6)
    vi.advanceTimersByTime(1000)
    expect(context.handleVideoEnd).toHaveBeenCalledWith(7)
  })

  it('backfills a missing duration as the length after the start', () => {
    const player = makePlayer(0, 300)
    installYouTube(player)
    youtubeStrategy.mount(ctx({ duration_seconds: null }))
    ready(player)
    expect(reportVideoMetadata).toHaveBeenCalledWith('streamer', 7, 210, expect.any(String))
  })
})
