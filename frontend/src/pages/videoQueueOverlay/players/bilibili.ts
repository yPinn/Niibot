import {
  BILIBILI_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

// `player.bilibili.com/player.html` is Bilibili's OFFICIAL embed player (the one
// its "share → embed" gives you), built to be iframed on third-party sites. It
// was swapped for `html5mobileplayer.html` in 56c4abd to hide chrome, but that
// mobile web player has heavier anti-embed checks and throws "本视频可能由于以下
// 原因导致无法正常播放" inside an OBS Browser Source (fresh cookie jar, no
// buvid3). The official embed is the better bet there.
//
// The player chrome (top info bar, bottom control bar, centred "更高清" promo)
// stays visible in OBS and we've accepted that — see
// docs/architecture/video-queue-platforms.md. The official embed has no param to
// hide it, the "更高清" layer is always-on, and the hover-gated bars never get
// the mouseleave that would fade them because OBS sends the page no pointer
// events at all. `pointerEvents = 'none'` just keeps it that way (a stray click
// would only pause the video).
//
// The undocumented postMessage API (`enablejsapi=1`) is still worth wiring for
// one thing: the player posts a `playerOperation-<json>` `ended` event, which
// advances the queue precisely instead of waiting out the timer ceiling.
// Bilibili's `-412` risk-control block means we usually have no real duration,
// so that ceiling is otherwise the only thing that ends a Bilibili entry.
function mount(ctx: MountContext): (() => void) | void {
  const {
    current,
    joinElapsed,
    currentId,
    muted,
    containerRef,
    notifyPlaybackStarted,
    handleVideoEnd,
  } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  const iframe = document.createElement('iframe')
  const startSeconds = Math.floor(joinElapsed)
  const base =
    `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(current.video_id)}` +
    `&autoplay=1&danmaku=0&high_quality=1&as_wide=1&enablejsapi=1&t=${startSeconds}`
  iframe.src = muted ? `${base}&muted=1` : base
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.style.pointerEvents = 'none'
  iframe.tabIndex = -1
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  iframe.addEventListener('load', () => notifyPlaybackStarted('best_effort'), { once: true })

  const onMessage = (event: MessageEvent) => {
    if (event.source !== iframe.contentWindow) return
    if (typeof event.data !== 'string' || !event.data.startsWith('playerOperation-')) return
    try {
      const payload = JSON.parse(event.data.slice('playerOperation-'.length))
      if (payload?.type === 'ended' || payload?.data === 'ended') handleVideoEnd(currentId)
    } catch {
      /* unrecognised event shape — ignore */
    }
  }
  window.addEventListener('message', onMessage)

  containerRef.current.appendChild(iframe)
  startTimerBasedEnd(ctx, BILIBILI_MAX_SECONDS)

  return () => window.removeEventListener('message', onMessage)
}

// Plain iframe — no external API script to preload, so no requiresApi.
export const bilibiliStrategy: PlayerStrategy = { requiresApi: null, mount }
