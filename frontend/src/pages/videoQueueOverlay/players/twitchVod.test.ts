import { afterEach, describe, expect, it, vi } from 'vitest'

import { reportClientError } from '@/lib/clientErrorReporter'

import { STALL_RECOVER_SECONDS, STALL_SKIP_SECONDS } from './shared'
import { twitchVodStrategy } from './twitchVod'
import type { MountContext } from './types'

vi.mock('@/lib/clientErrorReporter', () => ({ reportClientError: vi.fn() }))

/** Let the embed API load settle. */
async function settle() {
  for (let i = 0; i < 10; i++) await Promise.resolve()
}

function makePlayer() {
  return {
    play: vi.fn(),
    pause: vi.fn(),
    seek: vi.fn(),
    setMuted: vi.fn(),
    setVolume: vi.fn(),
    getCurrentTime: vi.fn(() => 0),
    getDuration: vi.fn(() => 0),
    getEnded: vi.fn(() => false),
    getVideo: vi.fn(() => 'v123456'),
    addEventListener: vi.fn(),
    destroy: vi.fn(),
  }
}

/** Invoke the listener the strategy registered for `event`. */
function fire(player: ReturnType<typeof makePlayer>, event: string) {
  for (const [name, cb] of player.addEventListener.mock.calls as [string, () => void][]) {
    if (name === event) cb()
  }
}

function installTwitch(player: ReturnType<typeof makePlayer>) {
  const Player = vi.fn(function () {
    return player
  }) as unknown as {
    (...a: unknown[]): unknown
    ENDED: string
    PLAYING: string
    PAUSE: string
    PLAYBACK_BLOCKED: string
    READY: string
    mock: { calls: unknown[][] }
  }
  Player.ENDED = 'video.ended'
  Player.PLAYING = 'video.play'
  Player.PAUSE = 'video.pause'
  Player.PLAYBACK_BLOCKED = 'video.blocked'
  Player.READY = 'video.ready'
  ;(window as unknown as { Twitch: unknown }).Twitch = { Player }
  return Player
}

function ctx(overrides: Partial<MountContext> = {}): MountContext {
  const div = document.createElement('div')
  return {
    current: {
      id: 7,
      video_id: '123456',
      title: 'A stream',
      duration_seconds: 600,
      is_vertical: false,
      start_seconds: 90,
      requested_by: 'viewer',
      source: 'chat',
      video_type: 'twitch_vod',
      started_at: null,
    },
    currentId: 7,
    joinElapsed: 0,
    isPreview: false,
    overlayKey: '11111111-1111-4111-8111-111111111111',
    muted: false,
    volumePercent: 35,
    username: 'streamer',
    containerRef: { current: div },
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
    ...overrides,
  } as MountContext
}

afterEach(() => {
  vi.useRealTimers()
  vi.mocked(reportClientError).mockClear()
  delete (window as unknown as { Twitch?: unknown }).Twitch
})

describe('twitchVodStrategy', () => {
  it('needs no external API up front (the embed loads its own)', () => {
    expect(twitchVodStrategy.requiresApi).toBeNull()
  })

  it('creates a controls-off Twitch.Player seeked to start + join offset', async () => {
    const player = makePlayer()
    const Player = installTwitch(player)
    const c = ctx({ joinElapsed: 10 })

    twitchVodStrategy.mount(c)

    await settle()

    expect(Player).toHaveBeenCalledTimes(1)
    const opts = Player.mock.calls[0][1] as Record<string, unknown>
    // Always muted at first: muted autoplay is what OBS lets through.
    expect(opts).toMatchObject({ video: '123456', controls: false, autoplay: true, muted: true })
    expect(opts.time).toBe('100s') // start_seconds 90 + joinElapsed 10
    expect(player.addEventListener).toHaveBeenCalledWith('video.ended', expect.any(Function))
    expect(player.addEventListener).toHaveBeenCalledWith('video.blocked', expect.any(Function))
    expect(player.setVolume).toHaveBeenCalledWith(0.35)
  })

  it('keeps the same joined playback position while muting a dashboard preview', async () => {
    const player = makePlayer()
    const Player = installTwitch(player)

    twitchVodStrategy.mount(ctx({ joinElapsed: 10, isPreview: true, muted: true }))

    await settle()

    const opts = Player.mock.calls[0][1] as Record<string, unknown>
    expect(opts).toMatchObject({ time: '100s', muted: true })
    fire(player, 'video.play')
    expect(player.setMuted).not.toHaveBeenCalledWith(false)
  })

  it('unmutes once playback starts', async () => {
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    twitchVodStrategy.mount(c)
    await settle()

    fire(player, 'video.play')
    expect(c.notifyPlaybackStarted).toHaveBeenCalledWith('confirmed')
    expect(player.setMuted).toHaveBeenLastCalledWith(false)
    expect(reportClientError).not.toHaveBeenCalled()
  })

  it('goes back to muted playback and reports when unmuting gets it paused', async () => {
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    twitchVodStrategy.mount(c)
    await settle()

    fire(player, 'video.play')
    player.play.mockClear()
    fire(player, 'video.pause')
    expect(player.setMuted).toHaveBeenLastCalledWith(true)
    expect(player.play).toHaveBeenCalled()
    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ errorCode: 'VIDEO_QUEUE.TWITCH_VOD_UNMUTE_REFUSED' })
    )
    expect(c.handleVideoEnd).not.toHaveBeenCalled()

    // The refusal is final for this entry: a later PLAYING doesn't retry sound.
    fire(player, 'video.play')
    expect(player.setMuted).toHaveBeenLastCalledWith(true)
  })

  it('a pause long after unmuting is an ordinary pause', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    twitchVodStrategy.mount(ctx())
    await settle()

    fire(player, 'video.play')
    vi.advanceTimersByTime(5000)
    fire(player, 'video.pause')
    expect(reportClientError).not.toHaveBeenCalled()
  })

  it('a block after unmuting keeps playing muted instead of skipping', async () => {
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    twitchVodStrategy.mount(c)
    await settle()

    fire(player, 'video.play')
    fire(player, 'video.blocked')
    expect(player.setMuted).toHaveBeenLastCalledWith(true)
    expect(c.handleVideoEnd).not.toHaveBeenCalled()
  })

  it('a block before playback starts advances as autoplay_blocked', async () => {
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    twitchVodStrategy.mount(c)
    await settle()

    fire(player, 'video.blocked')
    expect(c.handleVideoEnd).toHaveBeenCalledWith(7, 'autoplay_blocked')
  })

  it('advances as a provider error when the embed script fails to load', async () => {
    const c = ctx()
    const script = vi.spyOn(document.head, 'appendChild').mockImplementation(node => {
      queueMicrotask(() => (node as HTMLScriptElement).onerror?.(new Event('error')))
      return node
    })
    twitchVodStrategy.mount(c)
    await settle()
    expect(c.handleVideoEnd).toHaveBeenCalledWith(7, 'provider_error')
    script.mockRestore()
  })

  it('advances when the play window elapses', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    player.getCurrentTime.mockReturnValue(90 + 600) // start + full window

    const cleanup = twitchVodStrategy.mount(c)

    await settle()
    vi.advanceTimersByTime(1000)

    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    if (typeof cleanup === 'function') cleanup()
  })

  it('advances when Twitch autoplays a different VOD after the end', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()

    const cleanup = twitchVodStrategy.mount(c)

    await settle()
    vi.advanceTimersByTime(1000)
    expect(c.handleVideoEnd).not.toHaveBeenCalled()

    // ENDED missed; the player moved on to an unrelated VOD from 0.
    player.getVideo.mockReturnValue('v999')
    player.getCurrentTime.mockReturnValue(3)
    vi.advanceTimersByTime(1000)
    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    if (typeof cleanup === 'function') cleanup()
  })

  it('still ends on the window when getVideo is unavailable', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    player.getVideo.mockImplementation(() => {
      throw new Error('not supported')
    })
    installTwitch(player)
    const c = ctx()
    player.getCurrentTime.mockReturnValue(90 + 600)

    const cleanup = twitchVodStrategy.mount(c)

    await settle()
    vi.advanceTimersByTime(1000)
    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    if (typeof cleanup === 'function') cleanup()
  })

  it('skips straight to the end when a late join is already past the window', async () => {
    const player = makePlayer()
    const Player = installTwitch(player)
    const c = ctx({ joinElapsed: 700, current: { ...ctx().current, duration_seconds: 600 } })

    twitchVodStrategy.mount(c)
    await settle()

    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    expect(Player).not.toHaveBeenCalled()
  })

  it('re-seeks a mid-playback freeze, then skips it if it never clears', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    player.getCurrentTime.mockReturnValue(200) // 110s into the window, frozen
    const cleanup = twitchVodStrategy.mount(c)
    await settle()
    fire(player, 'video.play')
    player.play.mockClear()

    vi.advanceTimersByTime((STALL_RECOVER_SECONDS - 5) * 1000)
    expect(player.seek).not.toHaveBeenCalled()

    vi.advanceTimersByTime(10 * 1000)
    expect(player.seek).toHaveBeenCalledTimes(1)
    expect(player.seek).toHaveBeenCalledWith(200)
    expect(player.play).toHaveBeenCalled()
    expect(c.handleVideoEnd).not.toHaveBeenCalled()

    vi.advanceTimersByTime(STALL_SKIP_SECONDS * 1000)
    expect(c.handleVideoEnd).toHaveBeenCalledTimes(1)
    expect(c.handleVideoEnd).toHaveBeenCalledWith(7, 'provider_error')
    expect(reportClientError).toHaveBeenCalledWith(
      expect.objectContaining({ errorCode: 'VIDEO_QUEUE.PLAYBACK_STALLED' })
    )
    if (typeof cleanup === 'function') cleanup()
  })

  it('does not watch for stalls before playback starts', async () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    const cleanup = twitchVodStrategy.mount(c)
    await settle()

    vi.advanceTimersByTime((STALL_SKIP_SECONDS + 5) * 1000)
    expect(player.seek).not.toHaveBeenCalled()
    expect(c.handleVideoEnd).not.toHaveBeenCalled()
    if (typeof cleanup === 'function') cleanup()
  })

  it('destroys the player on cleanup', async () => {
    const player = makePlayer()
    installTwitch(player)
    const cleanup = twitchVodStrategy.mount(ctx())
    await settle()
    if (typeof cleanup === 'function') cleanup()
    expect(player.destroy).toHaveBeenCalled()
  })
})
