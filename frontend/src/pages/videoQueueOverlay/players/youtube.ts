import { reportVideoMetadata } from '@/api/videoQueue'

import { makeMountDiv } from './shared'
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
    muted,
    username,
    containerRef,
    leftContainerRef,
    rightContainerRef,
    playerRef,
    leftPlayerRef,
    rightPlayerRef,
    progressRef,
    setElapsed,
    handleVideoEnd,
  } = ctx

  // All-ready barrier: all players hold at autoplay:0 until every onReady has fired,
  // then startAll() calls playVideo() on all simultaneously — zero staggered delay.
  const totalPlayers = current.is_vertical ? 3 : 1
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
      for (const ref of [playerRef, leftPlayerRef, rightPlayerRef]) {
        if (ref.current)
          try {
            ref.current.seekTo(joinElapsed, true)
          } catch {
            /* ignore */
          }
      }
    }

    for (const ref of [playerRef, leftPlayerRef, rightPlayerRef]) {
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
      // Sync side players — resync if drift exceeds 0.3s
      for (const ref of [leftPlayerRef, rightPlayerRef]) {
        if (ref.current) {
          try {
            const st = ref.current.getCurrentTime()
            if (Math.abs(st - t) > 0.3) ref.current.seekTo(t, true)
          } catch {
            /* ignore */
          }
        }
      }
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
    if (readyCount >= totalPlayers) {
      clearTimeout(fallbackTimer)
      startAll()
    }
  }

  // 8s fallback in case a player never fires onReady
  fallbackTimer = setTimeout(startAll, 8000)

  // Muted side player for vertical video blurred columns.
  function createSidePlayer(
    containerRefArg: typeof leftContainerRef,
    playerRefArg: typeof leftPlayerRef
  ) {
    if (!containerRefArg.current) {
      onPlayerReady() // container not mounted — count as ready so barrier doesn't stall
      return
    }
    playerRefArg.current = new window.YT.Player(makeMountDiv(containerRefArg.current), {
      width: '100%',
      height: '100%',
      videoId: current.video_id,
      playerVars: {
        autoplay: 0,
        controls: 0,
        rel: 0,
        modestbranding: 1,
        mute: 1,
        iv_load_policy: 3,
        vq: 'highres',
      },
      events: { onReady: onPlayerReady },
    })
  }

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
      modestbranding: 1,
      iv_load_policy: 3,
      cc_load_policy: 3,
      mute: muted ? 1 : 0,
      vq: 'highres',
    },
    events: {
      onReady: event => {
        event.target.setPlaybackQuality('highres')
        const duration = event.target.getDuration()
        // Report duration to backend (fallback for entries where API returned null)
        if (duration > 0 && !current.duration_seconds && username) {
          reportVideoMetadata(username, currentId, Math.round(duration)).catch(() => {})
        }
        onPlayerReady()
      },
      onStateChange: event => {
        if (event.data === 1) {
          // YT.PlayerState.PLAYING — sync side panels
          for (const ref of [leftPlayerRef, rightPlayerRef]) {
            if (ref.current)
              try {
                ref.current.playVideo()
              } catch {
                /* ignore */
              }
          }
        }
        if (event.data === 2) {
          // YT.PlayerState.PAUSED — pause side panels in lockstep
          for (const ref of [leftPlayerRef, rightPlayerRef]) {
            if (ref.current)
              try {
                ref.current.pauseVideo()
              } catch {
                /* ignore */
              }
          }
        }
        if (event.data === 0) handleVideoEnd(currentId) // YT.PlayerState.ENDED
      },
      onError: () => handleVideoEnd(currentId),
    },
  })

  // Side players for vertical videos (blurred background columns)
  if (current.is_vertical) {
    createSidePlayer(leftContainerRef, leftPlayerRef)
    createSidePlayer(rightContainerRef, rightPlayerRef)
  }

  return () => {
    clearTimeout(fallbackTimer)
  }
}

export const youtubeStrategy: PlayerStrategy = { requiresApi: 'youtube', mount }

// Re-exported for VideoQueueOverlay.tsx's player refs, which are typed against this.
export type { YTPlayer }
