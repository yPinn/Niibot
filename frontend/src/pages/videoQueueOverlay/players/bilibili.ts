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
  // `muted=1` in the dashboard preview — a plain iframe can't be muted from the
  // host page, so it has to be a player URL param (html5mobileplayer supports it).
  iframe.src = `https://www.bilibili.com/blackboard/html5mobileplayer.html?bvid=${encodeURIComponent(current.video_id)}&autoplay=1&muted=${muted ? 1 : 0}&danmaku=0&hideDanmakuButton=1&noFullScreenButton=1&hideCoverInfo=1&hasMuteButton=0&t=${startSeconds}`
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = "autoplay 'src'; fullscreen 'src'"
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, BILIBILI_MAX_SECONDS)
}

// Bilibili is a plain iframe — no postMessage/control API to wait for, so no requiresApi.
export const bilibiliStrategy: PlayerStrategy = { requiresApi: null, mount }
