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

/**
 * End-detection strategy for platforms with no player-reported "ended" event
 * (Twitch Clip embed and the plain Bilibili iframe both only expose
 * duration_seconds up front, not playback state) — schedules handleVideoEnd
 * from the server-reported duration instead. Contrast with YouTube, which
 * detects end from real player events (onStateChange ENDED + a polling
 * fallback) and therefore does not use this helper.
 */
export function startTimerBasedEnd(ctx: MountContext): void {
  const { current, joinElapsed, currentId, clipTimerRef, handleVideoEnd } = ctx
  if (!current.duration_seconds) return
  const remaining = Math.max(0, current.duration_seconds - joinElapsed)
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
