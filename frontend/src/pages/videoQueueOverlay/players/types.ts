import type { RefObject } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'

export interface YTPlayer {
  playVideo(): void
  pauseVideo(): void
  destroy(): void
  getCurrentTime(): number
  getDuration(): number
  seekTo(seconds: number, allowSeekAhead?: boolean): void
  setPlaybackQuality(quality: string): void
}

export interface YTPlayerOptions {
  width?: number | string
  height?: number | string
  videoId?: string
  playerVars?: {
    autoplay?: 0 | 1
    controls?: 0 | 1
    rel?: 0 | 1
    modestbranding?: 0 | 1
    mute?: 0 | 1
    iv_load_policy?: 1 | 3
    cc_load_policy?: 1 | 3
    vq?: string
  }
  events?: {
    onReady?: (event: { target: YTPlayer }) => void
    onStateChange?: (event: { target: YTPlayer; data: number }) => void
    onError?: (event: { target: YTPlayer }) => void
  }
}

declare global {
  interface Window {
    YT: { Player: new (element: string | HTMLElement, options: YTPlayerOptions) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

declare global {
  interface Window {
    // Twitch clips embed via a plain clips.twitch.tv/embed iframe (no JS API).
    // This global is only for <TwitchPlayer>, the channel live-preview component.
    Twitch?: {
      Player?: new (
        element: HTMLElement,
        options: Record<string, unknown>
      ) => { destroy: () => void }
    }
  }
}

/** Everything a platform's mount() needs — owned by VideoQueueOverlay, passed in by reference. */
export interface MountContext {
  current: VideoQueueEntry
  currentId: number
  /** Seconds already elapsed since started_at — nonzero for a late-joining overlay. */
  joinElapsed: number
  isPreview: boolean
  /** Only used by the YouTube strategy, to report duration back when the API key is missing/quota-exhausted. */
  username: string | undefined
  containerRef: RefObject<HTMLDivElement | null>
  leftContainerRef: RefObject<HTMLDivElement | null>
  rightContainerRef: RefObject<HTMLDivElement | null>
  playerRef: RefObject<YTPlayer | null>
  leftPlayerRef: RefObject<YTPlayer | null>
  rightPlayerRef: RefObject<YTPlayer | null>
  progressRef: RefObject<ReturnType<typeof setInterval> | null>
  clipTimerRef: RefObject<ReturnType<typeof setTimeout> | null>
  currentIdRef: RefObject<number | null>
  setElapsed: (updater: number | ((prev: number) => number)) => void
  handleVideoEnd: (doneId: number) => void
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
  requiresApi: 'youtube' | null
  mount(ctx: MountContext): (() => void) | void
}
