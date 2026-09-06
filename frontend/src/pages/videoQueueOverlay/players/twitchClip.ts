import {
  CLIP_MAX_SECONDS,
  hasAlreadyEnded,
  startElapsedTracking,
  startTimerBasedEnd,
} from './shared'
import type { MountContext, PlayerStrategy } from './types'

function mount(ctx: MountContext): void {
  const { current, currentId, muted, containerRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  if (!containerRef.current) return
  containerRef.current.innerHTML = ''

  // clips.twitch.tv/embed is the only supported clip embed (docs: player.twitch.tv
  // is not valid for clips; Twitch.Embed's JS API only accepts
  // channel/video/collection and throws MissingParameterError on `clip`). This
  // iframe exposes no JS control or events API, so playback is fire-and-forget
  // and end-detection is timer-based, exactly like the Bilibili strategy.
  //
  // Twitch's own player gates unmuted autoplay on size + document visibility;
  // OBS renders the page "hidden", so a clip may still not autoplay with sound
  // there even though the browser autoplay policy is relaxed. There is no
  // parameter to force it and no unmute API — tracked as a known limitation.
  const params = new URLSearchParams({
    clip: current.video_id,
    parent: window.location.hostname,
    autoplay: 'true',
    muted: String(muted),
  })
  const iframe = document.createElement('iframe')
  iframe.src = `https://clips.twitch.tv/embed?${params.toString()}`
  iframe.style.cssText = 'width:100%;height:100%;border:none'
  // Explicit "'src'" delegation — the bare `autoplay` shorthand is not honored
  // by every CEF build OBS ships.
  iframe.allow = "autoplay 'src'; fullscreen 'src'"
  iframe.scrolling = 'no'
  containerRef.current.appendChild(iframe)

  startTimerBasedEnd(ctx, CLIP_MAX_SECONDS)
}

// Plain iframe, no external API to preload — same shape as Bilibili.
export const twitchClipStrategy: PlayerStrategy = { requiresApi: null, mount }
