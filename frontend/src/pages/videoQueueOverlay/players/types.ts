import type { RefObject } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'

export interface YTPlayer {
  playVideo(): void
  pauseVideo(): void
  destroy(): void
  getCurrentTime(): number
  getDuration(): number
  seekTo(seconds: number, allowSeekAhead?: boolean): void
  setVolume(volume: number): void
  mute(): void
  unMute(): void
}

export interface YTPlayerOptions {
  width?: number | string
  height?: number | string
  videoId?: string
  playerVars?: {
    autoplay?: 0 | 1
    controls?: 0 | 1
    rel?: 0 | 1
    mute?: 0 | 1
    iv_load_policy?: 1 | 3
  }
  events?: {
    onReady?: (event: { target: YTPlayer }) => void
    onStateChange?: (event: { target: YTPlayer; data: number }) => void
    onError?: (event: { target: YTPlayer }) => void
    onAutoplayBlocked?: (event: { target: YTPlayer }) => void
  }
}

declare global {
  interface Window {
    YT: { Player: new (element: string | HTMLElement, options: YTPlayerOptions) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

/** The subset of Twitch's embed player (`embed.twitch.tv/embed/v1.js`) the VOD
 *  strategy uses. Clips are NOT playable through this API — only `video`,
 *  `channel` and `collection` — so `twitchClip.ts` stays on its own path. */
export interface TwitchPlayerInstance {
  play(): void
  pause(): void
  seek(seconds: number): void
  setMuted(muted: boolean): void
  setVolume(volume: number): void
  getCurrentTime(): number
  getDuration(): number
  getEnded(): boolean
  addEventListener(event: string, cb: () => void): void
  destroy(): void
}

interface TwitchPlayerCtor {
  new (
    element: HTMLElement | string,
    options: {
      video?: string
      channel?: string
      parent?: string[]
      width?: number | string
      height?: number | string
      autoplay?: boolean
      muted?: boolean
      time?: string
      controls?: boolean
    }
  ): TwitchPlayerInstance
  PLAYING: string
  ENDED: string
  PAUSE: string
  READY?: string
  PLAYBACK_BLOCKED?: string
}

declare global {
  interface Window {
    Twitch?: { Player?: TwitchPlayerCtor }
  }
}

/** Everything a platform's mount() needs — owned by VideoQueueOverlay, passed in by reference. */
export interface MountContext {
  current: VideoQueueEntry
  currentId: number
  /** Seconds already elapsed since started_at — nonzero for a late-joining overlay. */
  joinElapsed: number
  isPreview: boolean
  /** Capability read from the URL fragment; absent URLs remain read-only. */
  overlayKey: string | null
  /**
   * Start playback muted. Currently `= isPreview`: the OBS overlay plays with
   * sound (OBS mixer owns audio), the dashboard preview must not blast audio at
   * the streamer — and browsers block unmuted autoplay outside OBS anyway.
   */
  muted: boolean
  /** Normalized output gain from settings, inclusive 0..100. */
  volumePercent: number
  /** Used by players to report missing duration metadata when a capability is available. */
  username: string | undefined
  containerRef: RefObject<HTMLDivElement | null>
  leftContainerRef: RefObject<HTMLDivElement | null>
  rightContainerRef: RefObject<HTMLDivElement | null>
  playerRef: RefObject<YTPlayer | null>
  leftPlayerRef: RefObject<YTPlayer | null>
  rightPlayerRef: RefObject<YTPlayer | null>
  progressRef: RefObject<ReturnType<typeof setInterval> | null>
  clipTimerRef: RefObject<ReturnType<typeof setTimeout> | null>
  playbackStartTimerRef: RefObject<ReturnType<typeof setTimeout> | null>
  currentIdRef: RefObject<number | null>
  setElapsed: (updater: number | ((prev: number) => number)) => void
  /** Clear the watchdog and report a qualified start. Iframe load is explicitly best-effort. */
  notifyPlaybackStarted: (signal?: 'confirmed' | 'best_effort') => void
  handleVideoEnd: (
    doneId: number,
    reason?: 'completed' | 'provider_error' | 'autoplay_blocked' | 'startup_timeout'
  ) => void
}

/**
 * One platform's playback behavior. `mount` performs the imperative DOM/player
 * setup (mirrors the platform branches previously inlined in VideoQueueOverlay's
 * player-creation effect) and returns an optional effect-cleanup callback —
 * only the YouTube strategy needs one today (clearing its ready-barrier fallback
 * timer), matching the pre-refactor behavior where Twitch Clip/Bilibili returned
 * nothing from that branch.
 */
export interface PlayerStrategy {
  /** Which external API must be ready before mount() can run; null needs none (plain iframe). */
  requiresApi: 'youtube' | 'twitch' | null
  mount(ctx: MountContext): (() => void) | void
}
