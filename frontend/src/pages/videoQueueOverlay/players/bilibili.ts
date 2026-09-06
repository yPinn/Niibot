import {
  BILIBILI_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

function mount(ctx: MountContext): void {
  const { current, joinElapsed, currentId, muted, containerRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  if (!containerRef.current) return
  containerRef.current.innerHTML = ''
  const iframe = document.createElement('iframe')
  const startSeconds = Math.floor(joinElapsed)
  // The OBS overlay URL is byte-for-byte the one that plays on staging — do NOT
  // add params here without testing in an actual OBS Browser Source, Bilibili's
  // player throws its generic "can't play" page on anything it dislikes.
  // `&muted=1` is appended ONLY for the muted dashboard preview (a plain iframe
  // has no host-side mute); html5mobileplayer treats an explicit `muted=0` as
  // "must play with sound" and errors when the browser then blocks that.
  const base =
    `https://www.bilibili.com/blackboard/html5mobileplayer.html?bvid=${encodeURIComponent(current.video_id)}` +
    `&autoplay=1&danmaku=0&hideDanmakuButton=1&noFullScreenButton=1&hideCoverInfo=1&hasMuteButton=0&t=${startSeconds}`
  iframe.src = muted ? `${base}&muted=1` : base
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, BILIBILI_MAX_SECONDS)
}

// Bilibili is a plain iframe — no postMessage/control API to wait for, so no requiresApi.
export const bilibiliStrategy: PlayerStrategy = { requiresApi: null, mount }
