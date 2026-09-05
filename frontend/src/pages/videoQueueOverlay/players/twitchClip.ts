import { hasAlreadyEnded, startElapsedTracking, startTimerBasedEnd } from './shared'
import type { MountContext, PlayerStrategy } from './types'

let _twitchReadyPromise: Promise<void> | null = null

export function loadTwitchEmbedAPI(): Promise<void> {
  if (_twitchReadyPromise) return _twitchReadyPromise
  _twitchReadyPromise = new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.Twitch?.Embed) {
      resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://embed.twitch.tv/embed/v1.js'
    script.onload = () => resolve()
    script.onerror = () => {
      _twitchReadyPromise = null
      reject(new Error('Failed to load Twitch Embed API'))
    }
    document.head.appendChild(script)
  })
  return _twitchReadyPromise
}

function mount(ctx: MountContext): void {
  const { current, currentId, isPreview, containerRef, currentIdRef, handleVideoEnd } = ctx

  if (hasAlreadyEnded(ctx)) {
    handleVideoEnd(currentId)
    return
  }

  startElapsedTracking(ctx)

  // Use Twitch.Embed JS API (not a raw iframe) so the player has a proper
  // postMessage channel with our page — raw iframes are blocked from autoplaying
  // because player.twitch.tv can't verify embed legitimacy without it.
  // autoplay:false + explicit play() in VIDEO_READY avoids any visibility
  // check during the overlayEnter animation (animation completes in ~600ms,
  // VIDEO_READY fires after the player finishes loading, typically 1-2s).
  if (!containerRef.current) return
  containerRef.current.innerHTML = ''
  // Twitch.Embed requires a string element ID as first argument
  const mountDiv = document.createElement('div')
  mountDiv.style.cssText = 'width:100%;height:100%'
  const mountId = `twitch-embed-${currentId}`
  mountDiv.id = mountId
  containerRef.current.appendChild(mountDiv)
  const embed = new window.Twitch!.Embed(mountId, {
    clip: current.video_id,
    parent: [window.location.hostname],
    layout: 'video',
    autoplay: false,
    muted: isPreview,
    width: '100%',
    height: '100%',
  })

  embed.addEventListener(window.Twitch!.Embed.VIDEO_READY, () => {
    // Guard: only play if this clip is still the current one
    if (currentIdRef.current === currentId) {
      embed.getPlayer().play()
    }
  })

  startTimerBasedEnd(ctx)
}

export const twitchClipStrategy: PlayerStrategy = { requiresApi: 'twitch', mount }
