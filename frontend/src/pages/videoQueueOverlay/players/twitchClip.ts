import {
  CLIP_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

function mount(ctx: MountContext): void {
  const { current, currentId, isPreview, containerRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  // clips.twitch.tv/embed is the only supported clip embed. Twitch.Embed (the
  // full-site JS API) only accepts channel/video/collection and throws
  // MissingParameterError on a `clip` option. This iframe exposes no JS control
  // or events API, so playback is fire-and-forget and end-detection is
  // timer-based, exactly like the Bilibili strategy.
  const params = new URLSearchParams({
    clip: current.video_id,
    parent: window.location.hostname,
    autoplay: 'true',
    muted: String(isPreview),
  })
  const iframe = document.createElement('iframe')
  iframe.src = `https://clips.twitch.tv/embed?${params.toString()}`
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  iframe.allow = 'autoplay; fullscreen'
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, CLIP_MAX_SECONDS)
}

// Plain iframe, no external API to preload — same shape as Bilibili.
export const twitchClipStrategy: PlayerStrategy = { requiresApi: null, mount }
