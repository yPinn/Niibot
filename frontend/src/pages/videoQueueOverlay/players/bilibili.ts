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
  // `player.bilibili.com/player.html` is Bilibili's OFFICIAL embed player (the
  // one its "share → embed" gives you), built to be iframed on third-party
  // sites. It was swapped for `html5mobileplayer.html` in 56c4abd purely to hide
  // player chrome — but the mobile web player has heavier anti-embed checks and
  // throws "本视频可能由于以下原因导致无法正常播放" inside an OBS Browser Source
  // (fresh cookie jar, no buvid3). The official embed is the better bet there;
  // `&danmaku=0` still drops the bullet comments.
  const base =
    `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(current.video_id)}` +
    `&autoplay=1&danmaku=0&high_quality=1&t=${startSeconds}`
  iframe.src = muted ? `${base}&muted=1` : base
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, BILIBILI_MAX_SECONDS)
}

// Bilibili is a plain iframe — no postMessage/control API to wait for, so no requiresApi.
export const bilibiliStrategy: PlayerStrategy = { requiresApi: null, mount }
