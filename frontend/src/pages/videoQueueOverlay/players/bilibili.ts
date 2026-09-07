import {
  BILIBILI_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

// `player.bilibili.com/player.html` is Bilibili's OFFICIAL embed player (the one
// its "share → embed" gives you), built to be iframed on third-party sites. It
// was swapped for `html5mobileplayer.html` in 56c4abd purely to hide chrome, but
// that mobile web player has heavier anti-embed checks and throws "本视频可能由于
// 以下原因导致无法正常播放" inside an OBS Browser Source (fresh cookie jar, no
// buvid3). The official embed is the better bet there.
//
// Its postMessage API is undocumented (`enablejsapi=1`): the parent can send
// `setPlayer-<json>` commands and the player posts `playerOperation-<json>`
// events back. We use it best-effort — a pause→play nudge collapses the player
// chrome to its idle state (the manual OBS workaround, scripted), and an `ended`
// event advances the queue precisely. Everything degrades to `pointer-events:
// none` + the timer ceiling if the player ignores us.
function mount(ctx: MountContext): (() => void) | void {
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
  const base =
    `https://player.bilibili.com/player.html?bvid=${encodeURIComponent(current.video_id)}` +
    `&autoplay=1&danmaku=0&high_quality=1&as_wide=1&enablejsapi=1&t=${startSeconds}`
  iframe.src = muted ? `${base}&muted=1` : base
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  // The overlay is display-only — never let the player see pointer activity, so
  // its controls / title bar / "更高清" nag auto-hide a few seconds after load.
  iframe.style.pointerEvents = 'none'
  iframe.tabIndex = -1
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'

  const send = (type: string, value: unknown) => {
    try {
      iframe.contentWindow?.postMessage(`setPlayer-${JSON.stringify({ type, value })}`, '*')
    } catch {
      /* cross-origin — the player just ignores it */
    }
  }
  iframe.addEventListener('load', () => {
    // Nudge the chrome into its idle/collapsed state.
    send('play', false)
    setTimeout(() => send('play', true), 300)
  })

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
