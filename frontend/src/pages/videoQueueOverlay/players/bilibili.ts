import {
  BILIBILI_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

function mount(ctx: MountContext): void {
  const { current, joinElapsed, currentId, containerRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  if (!containerRef.current) return
  containerRef.current.innerHTML = ''
  const iframe = document.createElement('iframe')
  const startSeconds = Math.floor(joinElapsed)
  iframe.src = `https://www.bilibili.com/blackboard/html5mobileplayer.html?bvid=${encodeURIComponent(current.video_id)}&autoplay=1&danmaku=0&hideDanmakuButton=1&noFullScreenButton=1&hideCoverInfo=1&hasMuteButton=0&t=${startSeconds}`
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, BILIBILI_MAX_SECONDS)
}

// Bilibili is a plain iframe — no postMessage/control API to wait for, so no requiresApi.
export const bilibiliStrategy: PlayerStrategy = { requiresApi: null, mount }
