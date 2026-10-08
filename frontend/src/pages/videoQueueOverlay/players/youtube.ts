import { reportVideoMetadata } from '@/api/videoQueue'

import { createStallWatch, makeMountDiv, mountPosterSidePanels } from './shared'
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

// The playhead can't run past the buffered media while really playing; a
// player that reports it anyway is advancing a clock, not showing frames.
const BUFFER_LAG_SECONDS = 3

function playheadOutranBuffer(player: YTPlayer, time: number, duration: number): boolean {
  let fraction = 0
  try {
    fraction = player.getVideoLoadedFraction()
  } catch {
    return false
  }
  // 0 means "not known yet" (right after a load or seek), not "nothing buffered".
  if (!(fraction > 0) || !(duration > 0)) return false
  return time > fraction * duration + BUFFER_LAG_SECONDS
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

  // Window model (same as Twitch VOD): play `duration_seconds` from
  // `start_seconds`. Without a segment, start is 0 and duration the whole video.
  const start = current.start_seconds || 0
  const segmentEnd = current.duration_seconds ? start + current.duration_seconds : null

  let readyCount = 0
  let allStarted = false
  let fallbackTimer = 0 as ReturnType<typeof setTimeout>
  // Armed on the first PLAYING; before that the startup watchdog owns a slow start.
  let playbackConfirmed = false
  // Set while a rebuilt player loads: its methods don't exist before onReady,
  // so the progress tick holds the last position and keeps counting the freeze.
  let reloadingAt: number | null = null
  const stallWatch = createStallWatch('youtube', {
    recover: () => {
      const player = playerRef.current
      if (!player) return
      try {
        player.seekTo(player.getCurrentTime(), true)
        player.playVideo()
      } catch {
        /* ignore */
      }
    },
    reload: () => {
      let at = start
      try {
        at = playerRef.current?.getCurrentTime() ?? start
      } catch {
        /* keep the segment start */
      }
      try {
        playerRef.current?.destroy()
      } catch {
        /* ignore */
      }
      reloadingAt = at
      playerRef.current = createPlayer(at, player => {
        try {
          player.seekTo(at, true)
          player.playVideo()
        } catch {
          /* ignore */
        }
        reloadingAt = null
      })
    },
    giveUp: () => {
      clearInterval(progressRef.current ?? undefined)
      progressRef.current = null
      handleVideoEnd(currentId, 'provider_error')
    },
  })

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

    // Seek to the segment start, plus how far in a late-joining overlay is.
    // playerVars.start already cues the start; only seek when it's off by >2s.
    if (joinElapsed > 2) {
      for (const ref of [playerRef]) {
        if (ref.current)
          try {
            ref.current.seekTo(start + joinElapsed, true)
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
      if (reloadingAt !== null) {
        stallWatch(reloadingAt, true)
        return
      }
      const t = playerRef.current.getCurrentTime()
      setElapsed(Math.max(0, t - start))
      // Segment end, plus an ENDED fallback for missed onStateChange events.
      const d = playerRef.current.getDuration()
      if ((segmentEnd !== null && t >= segmentEnd) || (d > 0 && t >= d - 0.5)) {
        clearInterval(progressRef.current ?? undefined)
        progressRef.current = null
        handleVideoEnd(currentId)
        return
      }
      if (playbackConfirmed) stallWatch(t, playheadOutranBuffer(playerRef.current, t, d))
    }, 1000)
  }

  function applyVolume(player: YTPlayer) {
    player.setVolume(volumePercent)
    if (muted || volumePercent === 0) player.mute()
    else player.unMute()
  }

  // Center player — pass an imperative child div so YT.Player's
  // parentNode.replaceChild() never detaches containerRef from the DOM
  function createPlayer(startAt: number, onReady: (player: YTPlayer) => void): YTPlayer {
    return new window.YT.Player(makeMountDiv(containerRef.current!), {
      width: '100%',
      height: '100%',
      videoId: current.video_id,
      playerVars: {
        autoplay: 0,
        controls: 0,
        rel: 0,
        iv_load_policy: 3,
        start: Math.floor(startAt),
        // Begin muted while the iframe initializes, then apply the explicit
        // preview/OBS mute state through the official API in onReady.
        mute: 1,
      },
      events: {
        onReady: event => {
          applyVolume(event.target)
          onReady(event.target)
        },
        onStateChange: event => {
          if (event.data === 1) {
            playbackConfirmed = true
            notifyPlaybackStarted('confirmed')
          }
          if (event.data === 0) handleVideoEnd(currentId) // YT.PlayerState.ENDED
        },
        onError: () => handleVideoEnd(currentId, 'provider_error'),
        onAutoplayBlocked: () => handleVideoEnd(currentId, 'autoplay_blocked'),
      },
    })
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

  playerRef.current = createPlayer(start + joinElapsed, player => {
    const duration = player.getDuration()
    // Report duration to backend (fallback for entries where API returned
    // null) — as the segment length, since that's what duration_seconds holds.
    if (duration > start && !current.duration_seconds && username && overlayKey && !isPreview) {
      reportVideoMetadata(username, currentId, Math.round(duration - start), overlayKey).catch(
        () => {}
      )
    }
    onPlayerReady()
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
