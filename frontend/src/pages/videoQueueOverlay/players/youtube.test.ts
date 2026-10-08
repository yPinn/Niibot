import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { reportVideoMetadata } from '@/api/videoQueue'
import { reportClientError } from '@/lib/clientErrorReporter'

import { STALL_RECOVER_SECONDS, STALL_RELOAD_SECONDS, STALL_SKIP_SECONDS } from './shared'
import type { MountContext, YTPlayer, YTPlayerOptions } from './types'
import { youtubeStrategy } from './youtube'

vi.mock('@/api/videoQueue', () => ({ reportVideoMetadata: vi.fn(() => Promise.resolve()) }))
vi.mock('@/lib/clientErrorReporter', () => ({ reportClientError: vi.fn() }))

function makePlayer(currentTime = 0, duration = 300) {
  return {
    playVideo: vi.fn(),
    pauseVideo: vi.fn(),
    destroy: vi.fn(),
    getCurrentTime: vi.fn(() => currentTime),
    getDuration: vi.fn(() => duration),
    getVideoLoadedFraction: vi.fn(() => 0),
    seekTo: vi.fn(),
    setVolume: vi.fn(),
    mute: vi.fn(),
    unMute: vi.fn(),
  }
}

let options: YTPlayerOptions | undefined

function installYouTube(player: ReturnType<typeof makePlayer>) {
  options = undefined
  const Player = vi.fn(function (_el: unknown, opts: YTPlayerOptions) {
    options = opts
    return player
  })
  ;(window as unknown as { YT: unknown }).YT = { Player }
  return Player
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

describe('youtubeStrategy mid-playback stall', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.mocked(reportClientError).mockClear()
  })

  /** Mounted, ready and confirmed PLAYING, with the playhead frozen at 100. */
  function playing() {
    const player = makePlayer(100)
    installYouTube(player)
    const context = ctx()
    youtubeStrategy.mount(context)
    ready(player)
    options?.events?.onStateChange?.({ target: player as unknown as YTPlayer, data: 1 })
    player.seekTo.mockClear()
    player.playVideo.mockClear()
    return { player, context }
  }

  it('leaves an ordinary rebuffer alone', () => {
    const { player, context } = playing()
    vi.advanceTimersByTime((STALL_RECOVER_SECONDS - 1) * 1000)
    player.getCurrentTime.mockReturnValue(101)
    vi.advanceTimersByTime((STALL_RECOVER_SECONDS - 1) * 1000)
    expect(player.seekTo).not.toHaveBeenCalled()
    expect(context.handleVideoEnd).not.toHaveBeenCalled()
  })

  it('re-seeks and plays once a freeze lasts long enough', () => {
    const { player, context } = playing()
    vi.advanceTimersByTime((STALL_RECOVER_SECONDS + 1) * 1000)
    expect(player.seekTo).toHaveBeenCalledTimes(1)
    expect(player.seekTo).toHaveBeenCalledWith(100, true)
    expect(player.playVideo).toHaveBeenCalledTimes(1)

    // Recovered: the playhead moves again, nothing is skipped.
    player.getCurrentTime.mockReturnValue(110)
    vi.advanceTimersByTime((STALL_SKIP_SECONDS - 10) * 1000)
    expect(context.handleVideoEnd).not.toHaveBeenCalled()
  })

  it('skips as a provider error and reports when the freeze never clears', () => {
    const { context } = playing()
    vi.advanceTimersByTime((STALL_SKIP_SECONDS + 5) * 1000)
    expect(context.handleVideoEnd).toHaveBeenCalledTimes(1)
    expect(context.handleVideoEnd).toHaveBeenCalledWith(7, 'provider_error')
    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ errorCode: 'VIDEO_QUEUE.PLAYBACK_STALLED' })
    )
  })

  it('rebuilds the player where it froze when a re-seek does not help', () => {
    const player = makePlayer(100)
    const Player = installYouTube(player)
    const context = ctx()
    youtubeStrategy.mount(context)
    ready(player)
    options?.events?.onStateChange?.({ target: player as unknown as YTPlayer, data: 1 })
    player.seekTo.mockClear()
    player.playVideo.mockClear()

    vi.advanceTimersByTime((STALL_RELOAD_SECONDS + 1) * 1000)
    expect(player.destroy).toHaveBeenCalledTimes(1)
    expect(Player).toHaveBeenCalledTimes(2)
    expect(options?.playerVars?.start).toBe(100)
    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ errorCode: 'VIDEO_QUEUE.PLAYBACK_RELOADED' })
    )

    // The fresh player resumes where the old one stood, re-applying volume.
    player.seekTo.mockClear()
    player.setVolume.mockClear()
    ready(player)
    expect(player.seekTo).toHaveBeenCalledWith(100, true)
    expect(player.setVolume).toHaveBeenCalledWith(35)

    let t = 100
    player.getCurrentTime.mockImplementation(() => (t += 1))
    vi.advanceTimersByTime(STALL_SKIP_SECONDS * 1000)
    expect(context.handleVideoEnd).not.toHaveBeenCalled()
    expect(Player).toHaveBeenCalledTimes(2)
  })

  it('keeps counting toward a skip while a rebuilt player never loads', () => {
    const { context } = playing()
    vi.advanceTimersByTime((STALL_RELOAD_SECONDS + 1) * 1000)
    // No onReady for the rebuilt player.
    vi.advanceTimersByTime((STALL_SKIP_SECONDS - STALL_RELOAD_SECONDS) * 1000)
    expect(context.handleVideoEnd).toHaveBeenCalledWith(7, 'provider_error')
  })

  it('treats a playhead running past the buffered media as frozen', () => {
    const { player } = playing()
    // 300s video buffered to 30s, while the reported playhead keeps advancing.
    player.getVideoLoadedFraction.mockReturnValue(0.1)
    let t = 100
    player.getCurrentTime.mockImplementation(() => (t += 1))
    vi.advanceTimersByTime((STALL_RECOVER_SECONDS + 1) * 1000)
    expect(player.seekTo).toHaveBeenCalledTimes(1)
  })

  it('does not treat an unknown buffer level as a freeze', () => {
    const { player, context } = playing()
    player.getVideoLoadedFraction.mockReturnValue(0)
    let t = 100
    player.getCurrentTime.mockImplementation(() => (t += 1))
    vi.advanceTimersByTime((STALL_SKIP_SECONDS + 5) * 1000)
    expect(player.seekTo).not.toHaveBeenCalled()
    expect(player.destroy).not.toHaveBeenCalled()
    expect(context.handleVideoEnd).not.toHaveBeenCalled()
  })

  it('is not armed before playback is confirmed', () => {
    const player = makePlayer(100)
    installYouTube(player)
    const context = ctx()
    youtubeStrategy.mount(context)
    ready(player)
    player.seekTo.mockClear()
    vi.advanceTimersByTime((STALL_SKIP_SECONDS + 1) * 1000)
    expect(player.seekTo).not.toHaveBeenCalled()
    expect(context.handleVideoEnd).not.toHaveBeenCalled()
  })
})
