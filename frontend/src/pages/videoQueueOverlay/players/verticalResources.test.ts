import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchInstagramReelSource } from '@/api/videoQueue'

import { instagramReelStrategy } from './instagramReel'
import type { MountContext, YTPlayer } from './types'
import { youtubeStrategy } from './youtube'

vi.mock('@/api/videoQueue', () => ({
  fetchInstagramReelSource: vi.fn(),
  reportVideoMetadata: vi.fn(),
}))

function player() {
  return {
    playVideo: vi.fn(),
    pauseVideo: vi.fn(),
    destroy: vi.fn(),
    getCurrentTime: vi.fn(() => 0),
    getDuration: vi.fn(() => 120),
    seekTo: vi.fn(),
    setVolume: vi.fn(),
    mute: vi.fn(),
    unMute: vi.fn(),
  } satisfies YTPlayer
}

function context(videoType: 'youtube' | 'instagram_reel'): MountContext {
  const center = document.createElement('div')
  const left = document.createElement('div')
  const right = document.createElement('div')
  return {
    current: {
      id: 7,
      video_id: 'vertical-id',
      title: 'Vertical video',
      duration_seconds: 120,
      is_vertical: true,
      thumbnail_url: 'https://images.example.test/poster.jpg',
      start_seconds: 0,
      requested_by: 'viewer',
      source: 'chat',
      video_type: videoType,
      started_at: null,
    },
    currentId: 7,
    joinElapsed: 0,
    isPreview: false,
    overlayKey: '11111111-1111-4111-8111-111111111111',
    muted: false,
    volumePercent: 35,
    username: 'streamer',
    containerRef: { current: center },
    leftContainerRef: { current: left },
    rightContainerRef: { current: right },
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
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  delete (window as unknown as { YT?: unknown }).YT
})

describe('vertical playback resource budget', () => {
  it('uses one YouTube player and poster-only side panels', () => {
    const instance = player()
    const Player = vi.fn(function () {
      return instance
    })
    ;(window as unknown as { YT: unknown }).YT = { Player }
    const ctx = context('youtube')

    const cleanup = youtubeStrategy.mount(ctx)

    expect(Player).toHaveBeenCalledTimes(1)
    expect(ctx.leftContainerRef.current?.style.backgroundImage).toContain('poster.jpg')
    expect(ctx.rightContainerRef.current?.style.backgroundImage).toContain('poster.jpg')
    expect(ctx.leftContainerRef.current?.children).toHaveLength(0)
    const options = Player.mock.calls[0]?.[1] as {
      events?: { onAutoplayBlocked?: (event: { target: YTPlayer }) => void }
    }
    options.events?.onAutoplayBlocked?.({ target: instance })
    expect(ctx.handleVideoEnd).toHaveBeenCalledWith(7, 'autoplay_blocked')
    if (typeof cleanup === 'function') cleanup()
  })

  it('uses one Instagram video element and poster-only side panels', async () => {
    vi.mocked(fetchInstagramReelSource).mockResolvedValue('https://cdn.example.test/reel.mp4')
    const ctx = context('instagram_reel')

    instagramReelStrategy.mount(ctx)
    await Promise.resolve()

    expect(ctx.containerRef.current?.querySelectorAll('video')).toHaveLength(1)
    expect(ctx.leftContainerRef.current?.querySelectorAll('video')).toHaveLength(0)
    expect(ctx.rightContainerRef.current?.querySelectorAll('video')).toHaveLength(0)
    expect(ctx.leftContainerRef.current?.style.backgroundImage).toContain('poster.jpg')
  })
})
