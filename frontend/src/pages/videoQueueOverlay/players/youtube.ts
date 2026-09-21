import { reportVideoMetadata } from '@/api/videoQueue'

import { makeMountDiv, mountPosterSidePanels } from './shared'
import type { MountContext, PlayerStrategy, YTPlayer } from './types'

let _ytReadyPromise: Promise<void> | null = null

export function loadYouTubeAPI(): Promise<void> {
  if (_ytReadyPromise) return _ytReadyPromise
  _ytReadyPromise = new Promise((resolve, reject) => {
    if (typeof window !== 'undefined' && window.YT?.Player) {
      resolve()
      return
    }
    window.onYouTubeIframeAPIReady = resolve
    const script = document.createElement('script')
    script.src = 'https://www.youtube.com/iframe_api'
    script.onerror = () => {
      _ytReadyPromise = null // allow retry on next mount
      reject(new Error('Failed to load YouTube IFrame API'))
    }
    document.head.appendChild(script)
  })
  return _ytReadyPromise
}

function mount(ctx: MountContext): () => void {
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
    leftContainerRef,
    rightContainerRef,
    playerRef,
    progressRef,
    setElapsed,
    notifyPlaybackStarted,
    handleVideoEnd,
  } = ctx

  let readyCount = 0
  let allStarted = false
  let fallbackTimer = 0 as ReturnType<typeof setTimeout>

  function startAll() {
    if (allStarted) return
    allStarted = true
    clearTimeout(fallbackTimer)

    // If elapsed >= duration the video has already ended — advance immediately
    // rather than creating a player that would instantly finish.
    if (current.duration_seconds && joinElapsed >= current.duration_seconds - 0.5) {
      clearInterval(progressRef.current ?? undefined)
      progressRef.current = null
      handleVideoEnd(currentId)
      return
    }

    // Seek all players to the correct position when joining mid-video (>2s in)
    if (joinElapsed > 2) {
      for (const ref of [playerRef]) {
        if (ref.current)
          try {
            ref.current.seekTo(joinElapsed, true)
          } catch {
            /* ignore */
          }
      }
    }

    for (const ref of [playerRef]) {
      if (ref.current)
        try {
          ref.current.playVideo()
        } catch {
          /* ignore */
        }
    }
    progressRef.current = setInterval(() => {
      if (!playerRef.current) return
      const t = playerRef.current.getCurrentTime()
      setElapsed(t)
      // ENDED fallback: polling check to catch missed onStateChange ENDED events
      const d = playerRef.current.getDuration()
      if (d > 0 && t >= d - 0.5) {
        clearInterval(progressRef.current ?? undefined)
        progressRef.current = null
        handleVideoEnd(currentId)
      }
    }, 1000)
  }

  function onPlayerReady() {
    readyCount++
    if (readyCount >= 1) {
      clearTimeout(fallbackTimer)
      startAll()
    }
  }

  // 8s fallback in case a player never fires onReady
  fallbackTimer = setTimeout(startAll, 8000)

  // Center player — pass an imperative child div so YT.Player's
  // parentNode.replaceChild() never detaches containerRef from the DOM
  playerRef.current = new window.YT.Player(makeMountDiv(containerRef.current!), {
    width: '100%',
    height: '100%',
    videoId: current.video_id,
    playerVars: {
      autoplay: 0,
      controls: 0,
      rel: 0,
      iv_load_policy: 3,
      // Begin muted while the iframe initializes, then apply the explicit
      // preview/OBS mute state through the official API in onReady.
      mute: 1,
    },
    events: {
      onReady: event => {
        event.target.setVolume(volumePercent)
        if (muted || volumePercent === 0) event.target.mute()
        else event.target.unMute()
        const duration = event.target.getDuration()
        // Report duration to backend (fallback for entries where API returned null)
        if (duration > 0 && !current.duration_seconds && username && overlayKey && !isPreview) {
          reportVideoMetadata(username, currentId, Math.round(duration), overlayKey).catch(() => {})
        }
        onPlayerReady()
      },
      onStateChange: event => {
        if (event.data === 1) {
          notifyPlaybackStarted('confirmed')
        }
        if (event.data === 0) handleVideoEnd(currentId) // YT.PlayerState.ENDED
      },
      onError: () => handleVideoEnd(currentId, 'provider_error'),
      onAutoplayBlocked: () => handleVideoEnd(currentId, 'autoplay_blocked'),
    },
  })

  if (current.is_vertical) {
    mountPosterSidePanels(current, [leftContainerRef, rightContainerRef])
  }

  return () => {
    clearTimeout(fallbackTimer)
  }
}

export const youtubeStrategy: PlayerStrategy = { requiresApi: 'youtube', mount }

// Re-exported for VideoQueueOverlay.tsx's player refs, which are typed against this.
export type { YTPlayer }
