import { afterEach, describe, expect, it, vi } from 'vitest'

import { twitchVodStrategy } from './twitchVod'
import type { MountContext } from './types'

vi.mock('@/api/videoQueue', () => ({ reportVideoMetadata: vi.fn() }))

function makePlayer() {
  return {
    play: vi.fn(),
    pause: vi.fn(),
    seek: vi.fn(),
    setMuted: vi.fn(),
    getCurrentTime: vi.fn(() => 0),
    getDuration: vi.fn(() => 0),
    getEnded: vi.fn(() => false),
    addEventListener: vi.fn(),
    destroy: vi.fn(),
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
    mock: { calls: unknown[][] }
  }
  Player.ENDED = 'video.ended'
  Player.PLAYING = 'video.play'
  Player.PAUSE = 'video.pause'
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
    muted: false,
    username: 'streamer',
    containerRef: { current: div },
    leftContainerRef: { current: null },
    rightContainerRef: { current: null },
    playerRef: { current: null },
    leftPlayerRef: { current: null },
    rightPlayerRef: { current: null },
    progressRef: { current: null },
    clipTimerRef: { current: null },
    currentIdRef: { current: null },
    setElapsed: vi.fn(),
    handleVideoEnd: vi.fn(),
    ...overrides,
  } as MountContext
}

afterEach(() => {
  vi.useRealTimers()
  delete (window as unknown as { Twitch?: unknown }).Twitch
})

describe('twitchVodStrategy', () => {
  it('needs the twitch embed API', () => {
    expect(twitchVodStrategy.requiresApi).toBe('twitch')
  })

  it('creates a controls-off Twitch.Player seeked to start + join offset', () => {
    const player = makePlayer()
    const Player = installTwitch(player)
    const c = ctx({ joinElapsed: 10 })

    twitchVodStrategy.mount(c)

    expect(Player).toHaveBeenCalledTimes(1)
    const opts = Player.mock.calls[0][1] as Record<string, unknown>
    expect(opts).toMatchObject({ video: '123456', controls: false, autoplay: true, muted: false })
    expect(opts.time).toBe('100s') // start_seconds 90 + joinElapsed 10
    expect(player.addEventListener).toHaveBeenCalledWith('video.ended', expect.any(Function))
  })

  it('advances when the play window elapses', () => {
    vi.useFakeTimers()
    const player = makePlayer()
    installTwitch(player)
    const c = ctx()
    player.getCurrentTime.mockReturnValue(90 + 600) // start + full window

    const cleanup = twitchVodStrategy.mount(c)
    vi.advanceTimersByTime(1000)

    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    if (typeof cleanup === 'function') cleanup()
  })

  it('skips straight to the end when a late join is already past the window', () => {
    const player = makePlayer()
    const Player = installTwitch(player)
    const c = ctx({ joinElapsed: 700, current: { ...ctx().current, duration_seconds: 600 } })

    twitchVodStrategy.mount(c)

    expect(c.handleVideoEnd).toHaveBeenCalledWith(7)
    expect(Player).not.toHaveBeenCalled()
  })

  it('destroys the player on cleanup', () => {
    const player = makePlayer()
    installTwitch(player)
    const cleanup = twitchVodStrategy.mount(ctx())
    if (typeof cleanup === 'function') cleanup()
    expect(player.destroy).toHaveBeenCalled()
  })
})
