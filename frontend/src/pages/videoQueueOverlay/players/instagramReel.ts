import { fetchInstagramReelSource, reportVideoMetadata } from '@/api/videoQueue'

import { hasAlreadyEnded } from './shared'
import type { MountContext, PlayerStrategy } from './types'

// Instagram has no embeddable fallback surface (unlike Twitch's
// clips.twitch.tv/embed) — a Reel can only be played by resolving its signed
// CDN MP4 through the self-hosted InstaFix proxy and playing it in a host
// `<video>`, same mechanism as twitchClip.ts's <video> path. Because there's
// no fallback, a resolve failure or a <video> error skips the entry
// immediately instead of degrading to a lesser embed — the queue must never
// stall (see docs/architecture/video-queue-platforms.md).
//
// Most Reels are 9:16, but not all — a landscape source video keeps its own
// aspect ratio when posted as a Reel. current.is_vertical reflects that
// per-entry detection (backend: instafix_client._extract_is_vertical), so
// only genuinely vertical Reels get the blurred-side-column treatment,
// same as YouTube Shorts. Unlike youtube.ts's side panels — full separate
// YT.Player instances with an all-ready barrier and state-change sync — a
// <video> element has no "player object" abstraction to juggle, so the side
// panels here are just two more <video>s pointing at the same resolved URL,
// seeked/played off their own loadedmetadata and nudged back in sync
// (>0.3s drift) from the center video's progress tick.

const SIDE_DRIFT_SECONDS = 0.3

function makeVideoEl(url: string, muted: boolean, cover: boolean): HTMLVideoElement {
  const video = document.createElement('video')
  video.src = url
  video.autoplay = true
  video.muted = muted
  video.playsInline = true
  video.style.cssText = cover
    ? 'width:100%;height:100%;object-fit:cover'
    : 'width:100%;height:100%;object-fit:contain;background:#000'
  return video
}

function mountSidePanel(container: HTMLDivElement, url: string, joinElapsed: number) {
  container.innerHTML = ''
  const video = makeVideoEl(url, /* muted */ true, /* cover */ true)
  video.addEventListener('loadedmetadata', () => {
    if (joinElapsed > 1 && joinElapsed < video.duration) {
      video.currentTime = joinElapsed
    }
    void video.play().catch(() => {})
  })
  container.appendChild(video)
  return video
}

function mountVideo(ctx: MountContext, url: string): void {
  const {
    current,
    currentId,
    joinElapsed,
    muted,
    username,
    containerRef,
    leftContainerRef,
    rightContainerRef,
    progressRef,
    setElapsed,
    handleVideoEnd,
  } = ctx
  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  const video = makeVideoEl(url, muted, false)

  const leftVideo =
    current.is_vertical && leftContainerRef.current
      ? mountSidePanel(leftContainerRef.current, url, joinElapsed)
      : null
  const rightVideo =
    current.is_vertical && rightContainerRef.current
      ? mountSidePanel(rightContainerRef.current, url, joinElapsed)
      : null

  video.addEventListener('loadedmetadata', () => {
    if (video.duration && !current.duration_seconds && username) {
      reportVideoMetadata(username, currentId, Math.round(video.duration)).catch(() => {})
    }
    if (joinElapsed > 1 && joinElapsed < video.duration) {
      video.currentTime = joinElapsed
    }
    void video.play().catch(() => {})
  })
  video.addEventListener('ended', () => handleVideoEnd(currentId))
  // No fallback embed exists for Instagram — a media error after the source
  // resolved (expired token, CDN 403) skips straight to the next entry.
  video.addEventListener(
    'error',
    () => {
      console.warn('[instagramReel] <video> error after source resolved, skipping entry')
      if (progressRef.current) clearInterval(progressRef.current)
      progressRef.current = null
      handleVideoEnd(currentId)
    },
    { once: true }
  )

  setElapsed(joinElapsed)
  progressRef.current = setInterval(() => {
    setElapsed(video.currentTime)
    for (const side of [leftVideo, rightVideo]) {
      if (!side) continue
      if (Math.abs(side.currentTime - video.currentTime) > SIDE_DRIFT_SECONDS) {
        side.currentTime = video.currentTime
      }
      void side.play().catch(() => {})
    }
  }, 1000)
  containerRef.current.appendChild(video)
}

function mount(ctx: MountContext): (() => void) | void {
  const { currentId, username, containerRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }
  if (!containerRef.current) return

  let cancelled = false
  const resolve = username
    ? fetchInstagramReelSource(username, currentId)
    : Promise.resolve<string | null>(null)

  void resolve
    .then(reelUrl => {
      if (cancelled || !containerRef.current) return
      if (reelUrl) {
        mountVideo(ctx, reelUrl)
      } else {
        console.warn('[instagramReel] source resolve failed, skipping entry')
        handleVideoEnd(currentId)
      }
    })
    .catch(() => {
      if (!cancelled) handleVideoEnd(currentId)
    })

  return () => {
    cancelled = true
  }
}

export const instagramReelStrategy: PlayerStrategy = { requiresApi: null, mount }
