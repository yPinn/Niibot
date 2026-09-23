import type { RefObject } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'

import type { MountContext, YTPlayer } from './types'

/** Destroy all active YT players, clear the clip timer, and stop the progress interval. */
export function destroyAllPlayers(
  refs: Array<RefObject<YTPlayer | null>>,
  progressRef: RefObject<ReturnType<typeof setInterval> | null>,
  clipTimerRef: RefObject<ReturnType<typeof setTimeout> | null>,
  playbackStartTimerRef: RefObject<ReturnType<typeof setTimeout> | null>,
  containerRef: RefObject<HTMLDivElement | null>,
  setElapsed: (v: number) => void,
  // Side-panel containers (blurred columns for vertical video): YouTube's YT.Player
  // instances there clean up via ref.current.destroy() above, but Instagram Reel's
  // side panels are plain <video> elements with no player-object abstraction — they
  // need their own explicit clear, same as containerRef, or a leftover element would
  // persist into the next mount.
  sideContainerRefs: Array<RefObject<HTMLDivElement | null>> = []
) {
  for (const ref of refs) {
    if (ref.current) {
      try {
        ref.current.destroy()
      } catch {
        /* ignore */
      }
      ref.current = null
    }
  }
  if (progressRef.current) {
    clearInterval(progressRef.current ?? undefined)
    progressRef.current = null
  }
  if (clipTimerRef.current) {
    clearTimeout(clipTimerRef.current)
    clipTimerRef.current = null
  }
  if (playbackStartTimerRef.current) {
    clearTimeout(playbackStartTimerRef.current)
    playbackStartTimerRef.current = null
  }
  // Clear any iframe/video left by the previous entry's player
  if (containerRef.current) {
    containerRef.current.innerHTML = ''
  }
  for (const ref of sideContainerRefs) {
    if (ref.current) {
      ref.current.innerHTML = ''
      ref.current.style.backgroundImage = ''
    }
  }
  setElapsed(0)
}

/**
 * Fill vertical-video side columns with the provider poster instead of
 * decoding/streaming the media three times. The dark overlay and CSS blur keep
 * these decorative; the centre remains the only active player.
 */
export function mountPosterSidePanels(
  current: Pick<VideoQueueEntry, 'thumbnail_url'>,
  sideContainerRefs: Array<RefObject<HTMLDivElement | null>>
): void {
  for (const ref of sideContainerRefs) {
    const container = ref.current
    if (!container) continue
    container.innerHTML = ''
    container.style.backgroundImage = current.thumbnail_url
      ? `url("${current.thumbnail_url.replaceAll('"', '%22')}")`
      : ''
    container.style.backgroundPosition = 'center'
    container.style.backgroundRepeat = 'no-repeat'
    container.style.backgroundSize = 'cover'
  }
}

/** Create a fresh full-size mount div inside a container, clearing previous children. */
export function makeMountDiv(container: HTMLDivElement): HTMLDivElement {
  const div = document.createElement('div')
  div.style.cssText = 'width:100%;height:100%'
  container.innerHTML = ''
  container.appendChild(div)
  return div
}

/**
 * True if the video has already finished by the time a late-joining overlay
 * connects (joinElapsed caught up to or passed duration_seconds). Shared by
 * every strategy so a stale/expired entry never spins up a player just to
 * have it finish instantly.
 */
export function hasAlreadyEnded(ctx: Pick<MountContext, 'current' | 'joinElapsed'>): boolean {
  const { current, joinElapsed } = ctx
  return Boolean(current.duration_seconds && joinElapsed >= current.duration_seconds - 0.5)
}

// Upper bound on how long a timer-based platform holds the queue when the
// server could not supply a duration. Without this the video would play
// forever (recoverable only via `!vq skip`). A Twitch clip is at most 60s;
// Bilibili has no natural cap, so this is a "something is wrong, move on" value.
export const CLIP_MAX_SECONDS = 90
export const BILIBILI_MAX_SECONDS = 600

/**
 * End-detection strategy for platforms with no player-reported "ended" event
 * (the Twitch clip embed and the plain Bilibili iframe both only expose
 * duration_seconds up front, not playback state) — schedules handleVideoEnd
 * from the server-reported duration instead. Contrast with YouTube, which
 * detects end from real player events (onStateChange ENDED + a polling
 * fallback) and therefore does not use this helper.
 *
 * `fallbackMaxSeconds` is used when duration_seconds is missing (Bilibili's
 * unofficial metadata endpoint fails from datacenter IPs) so the queue always
 * advances instead of stalling on one bad fetch.
 */
export function startTimerBasedEnd(ctx: MountContext, fallbackMaxSeconds: number): void {
  const { current, joinElapsed, currentId, clipTimerRef, handleVideoEnd } = ctx
  const total =
    current.duration_seconds && current.duration_seconds > 0
      ? current.duration_seconds
      : fallbackMaxSeconds
  const remaining = Math.max(0, total - joinElapsed)
  clipTimerRef.current = setTimeout(() => handleVideoEnd(currentId), remaining * 1000 + 500)
}

/**
 * Initialise elapsed to joinElapsed (for a late-joining overlay) and start the
 * once-per-second ticker. Shared by Twitch Clip and Bilibili, which have no
 * player-reported current-time and so just count up locally; YouTube instead
 * drives its ticker off the real player's getCurrentTime() and does not use this.
 */
export function startElapsedTracking(
  ctx: Pick<MountContext, 'joinElapsed' | 'progressRef' | 'setElapsed'>
): void {
  ctx.setElapsed(ctx.joinElapsed)
  ctx.progressRef.current = setInterval(() => {
    ctx.setElapsed(prev => prev + 1)
  }, 1000)
}
