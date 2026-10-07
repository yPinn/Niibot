import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VideoQueueLiveInsert } from '@/api/videoQueue'

import { mountLiveInsert, OFFLINE_GRACE_MS } from './liveInsert'
import type { YTPlayerOptions } from './types'

function insert(overrides: Partial<VideoQueueLiveInsert> = {}): VideoQueueLiveInsert {
  return {
    id: 5,
    source_type: 'twitch_live',
    source_id: 'lofistreamer',
    title: 'beats',
    creator_name: 'LofiStreamer',
    thumbnail_url: null,
    volume_percent: 30,
    audio_only: false,
    started_at: null,
    ...overrides,
  }
}

function installTwitch() {
  const listeners: Record<string, () => void> = {}
  const player = {
    play: vi.fn(),
    setVolume: vi.fn(),
    setMuted: vi.fn(),
    destroy: vi.fn(),
    addEventListener: vi.fn((event: string, cb: () => void) => {
      listeners[event] = cb
    }),
  }
  const Player = Object.assign(
    vi.fn(function () {
      return player
    }),
    {
      ENDED: 'ended',
      PLAYING: 'playing',
      PAUSE: 'pause',
      READY: 'ready',
      ONLINE: 'online',
      OFFLINE: 'offline',
    }
  )
  ;(window as unknown as { Twitch: unknown }).Twitch = { Player }
  return { Player, player, fire: (event: string) => listeners[event]?.() }
}

describe('mountLiveInsert — Twitch channel', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    delete (window as unknown as { Twitch?: unknown }).Twitch
  })

  it('plays the channel (not a video) with controls off at the insert volume', () => {
    const { Player, player } = installTwitch()
    mountLiveInsert({
      insert: insert(),
      container: document.createElement('div'),
      muted: false,
      onEnded: vi.fn(),
    })
    const opts = Player.mock.calls[0][1] as Record<string, unknown>
    expect(opts).toMatchObject({ channel: 'lofistreamer', controls: false, autoplay: true })
    expect(opts.video).toBeUndefined()
    expect(player.setVolume).toHaveBeenCalledWith(0.3)
    expect(player.setMuted).toHaveBeenLastCalledWith(false)
  })

  it('rides out a brief offline blip but ends after the grace period', () => {
    const { fire } = installTwitch()
    const onEnded = vi.fn()
    mountLiveInsert({
      insert: insert(),
      container: document.createElement('div'),
      muted: false,
      onEnded,
    })

    fire('offline')
    vi.advanceTimersByTime(OFFLINE_GRACE_MS - 1000)
    fire('online')
    vi.advanceTimersByTime(OFFLINE_GRACE_MS)
    expect(onEnded).not.toHaveBeenCalled()

    fire('offline')
    vi.advanceTimersByTime(OFFLINE_GRACE_MS)
    expect(onEnded).toHaveBeenCalledOnce()
    expect(onEnded).toHaveBeenCalledWith('offline')
  })

  it('applies a volume change without remounting', () => {
    const { Player, player } = installTwitch()
    const controller = mountLiveInsert({
      insert: insert(),
      container: document.createElement('div'),
      muted: false,
      onEnded: vi.fn(),
    })
    controller?.setVolume(0, false)
    expect(player.setMuted).toHaveBeenLastCalledWith(true)
    expect(Player).toHaveBeenCalledTimes(1)
  })

  it('destroy clears a pending offline timer', () => {
    const { fire, player } = installTwitch()
    const onEnded = vi.fn()
    const controller = mountLiveInsert({
      insert: insert(),
      container: document.createElement('div'),
      muted: false,
      onEnded,
    })
    fire('offline')
    controller?.destroy()
    vi.advanceTimersByTime(OFFLINE_GRACE_MS)
    expect(onEnded).not.toHaveBeenCalled()
    expect(player.destroy).toHaveBeenCalled()
  })
})

describe('mountLiveInsert — YouTube live', () => {
  afterEach(() => {
    delete (window as unknown as { YT?: unknown }).YT
  })

  it('plays the live video and ends when the broadcast ends', () => {
    let options: YTPlayerOptions | undefined
    const player = {
      playVideo: vi.fn(),
      setVolume: vi.fn(),
      mute: vi.fn(),
      unMute: vi.fn(),
      destroy: vi.fn(),
    }
    ;(window as unknown as { YT: unknown }).YT = {
      Player: vi.fn(function (_el: unknown, opts: YTPlayerOptions) {
        options = opts
        return player
      }),
    }
    const onEnded = vi.fn()
    mountLiveInsert({
      insert: insert({ source_type: 'youtube_live', source_id: 'jfKfPfyJRdk' }),
      container: document.createElement('div'),
      muted: false,
      onEnded,
    })
    expect(options?.videoId).toBe('jfKfPfyJRdk')

    options?.events?.onReady?.({ target: player as never })
    expect(player.setVolume).toHaveBeenCalledWith(30)
    expect(player.playVideo).toHaveBeenCalled()

    options?.events?.onStateChange?.({ target: player as never, data: 0 })
    expect(onEnded).toHaveBeenCalledWith('ended')
  })
})
