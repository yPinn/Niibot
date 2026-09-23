import { fetchTwitchClipSource, reportVideoMetadata } from '@/api/videoQueue'

import {
  CLIP_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

// `clips.twitch.tv/embed` cannot autoplay inside an OBS Browser Source: Twitch's
// player gates unmuted autoplay on document visibility and OBS renders the page
// "hidden". The signed-MP4 `<video>` path plays via an imperative `video.play()`
// (like YouTube's `playVideo()`), which the browser autoplay policy — relaxed in
// OBS — actually honours, and it gives real `ended` / `timeupdate` events instead
// of the timer ceiling. The iframe stays as the fallback for when the
// (unofficial) source resolve fails. See docs/architecture/video-queue-platforms.md.

function mountIframe(ctx: MountContext): void {
  const { current, muted, containerRef, notifyPlaybackStarted } = ctx
  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  const params = new URLSearchParams({
    clip: current.video_id,
    parent: window.location.hostname,
    autoplay: 'true',
    muted: String(muted),
  })
  const iframe = document.createElement('iframe')
  iframe.src = `https://clips.twitch.tv/embed?${params.toString()}`
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  iframe.addEventListener('load', () => notifyPlaybackStarted('best_effort'), { once: true })
  containerRef.current.appendChild(iframe)

  startElapsedTracking(ctx)
  startTimerBasedEnd(ctx, CLIP_MAX_SECONDS)
}

function mountVideo(ctx: MountContext, url: string): void {
  const {
    current,
    currentId,
    joinElapsed,
    isPreview,
    overlayKey,
    muted,
    volumePercent,
    username,
    containerRef,
    progressRef,
    setElapsed,
    notifyPlaybackStarted,
    handleVideoEnd,
  } = ctx
  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  const video = document.createElement('video')
  video.src = url
  video.autoplay = true
  video.volume = volumePercent / 100
  video.muted = muted || volumePercent === 0
  video.playsInline = true
  video.style.cssText = 'width:100%;height:100%;object-fit:contain;background:#000'

  video.addEventListener('loadedmetadata', () => {
    if (video.duration && !current.duration_seconds && username && overlayKey && !isPreview) {
      reportVideoMetadata(username, currentId, Math.round(video.duration), overlayKey).catch(
        () => {}
      )
    }
    if (joinElapsed > 1 && joinElapsed < video.duration) {
      video.currentTime = joinElapsed
    }
    void video.play().catch(() => {})
  })
  video.addEventListener('ended', () => handleVideoEnd(currentId))
  video.addEventListener('playing', () => notifyPlaybackStarted('confirmed'), { once: true })
  // A media error after the source resolved (expired token, CDN 403, a
  // media-src the CSP doesn't cover) — drop back to the embed iframe, whose own
  // timer ceiling still advances the queue.
  video.addEventListener(
    'error',
    () => {
      if (progressRef.current) clearInterval(progressRef.current)
      progressRef.current = null
      mountIframe(ctx)
    },
    { once: true }
  )

  setElapsed(joinElapsed)
  progressRef.current = setInterval(() => setElapsed(video.currentTime), 1000)
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
    ? fetchTwitchClipSource(username, currentId)
    : Promise.resolve<string | null>(null)

  void resolve
    .then(clipUrl => {
      if (cancelled || !containerRef.current) return
      if (clipUrl) mountVideo(ctx, clipUrl)
      else mountIframe(ctx)
    })
    .catch(() => {
      if (!cancelled && containerRef.current) mountIframe(ctx)
    })

  return () => {
    cancelled = true
  }
}

export const twitchClipStrategy: PlayerStrategy = { requiresApi: null, mount }
