import type { RefObject } from 'react'

import type { MountContext, YTPlayer } from './types'

/** Destroy all active YT players, clear the clip timer, and stop the progress interval. */
export function destroyAllPlayers(
  refs: Array<RefObject<YTPlayer | null>>,
  progressRef: RefObject<ReturnType<typeof setInterval> | null>,
  clipTimerRef: RefObject<ReturnType<typeof setTimeout> | null>,
  containerRef: RefObject<HTMLDivElement | null>,
  setElapsed: (v: number) => void
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
  // Clear any iframe left by a Twitch clip or Bilibili player
  if (containerRef.current) {
    containerRef.current.innerHTML = ''
  }
  setElapsed(0)
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
