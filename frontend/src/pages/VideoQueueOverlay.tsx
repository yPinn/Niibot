import { useEffect, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'

import {
  advanceVideoQueue,
  getPublicVideoQueueState,
  type PublicVideoQueueState,
  reportVideoMetadata,
  type VideoQueueEntry,
} from '@/api/videoQueue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ---------------------------------------------------------------------------
// YouTube IFrame API — minimal inline types
// ---------------------------------------------------------------------------

interface YTPlayer {
  playVideo(): void
  destroy(): void
  getCurrentTime(): number
  getDuration(): number
  getPlayerState(): number
}

interface YTPlayerOptions {
  width?: number | string
  height?: number | string
  videoId?: string
  playerVars?: {
    autoplay?: 0 | 1
    controls?: 0 | 1
    rel?: 0 | 1
    modestbranding?: 0 | 1
  }
  events?: {
    onReady?: (event: { target: YTPlayer }) => void
    onStateChange?: (event: { target: YTPlayer; data: number }) => void
    onError?: (event: { target: YTPlayer }) => void
    onAutoplayBlocked?: (event: { target: YTPlayer }) => void
  }
}

declare global {
  interface Window {
    YT: { Player: new (element: string | HTMLElement, options: YTPlayerOptions) => YTPlayer }
    onYouTubeIframeAPIReady?: () => void
  }
}

// ---------------------------------------------------------------------------
// YouTube API loader (singleton promise)
// ---------------------------------------------------------------------------

let _ytReadyPromise: Promise<void> | null = null

function loadYouTubeAPI(): Promise<void> {
  if (_ytReadyPromise) return _ytReadyPromise
  _ytReadyPromise = new Promise(resolve => {
    if (typeof window !== 'undefined' && window.YT?.Player) {
      resolve()
      return
    }
    window.onYouTubeIframeAPIReady = resolve
    const script = document.createElement('script')
    script.src = 'https://www.youtube.com/iframe_api'
    document.head.appendChild(script)
  })
  return _ytReadyPromise
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const POLL_INTERVAL = 5_000

function formatSeconds(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// ---------------------------------------------------------------------------
// Info bar shown over the video
// ---------------------------------------------------------------------------

function InfoBar({
  entry,
  elapsed,
  queueCount,
  totalQueuedDuration,
}: {
  entry: VideoQueueEntry
  elapsed: number
  queueCount: number
  totalQueuedDuration: number | null
}) {
  const duration = entry.duration_seconds
  const progress = duration && duration > 0 ? Math.min(elapsed / duration, 1) : 0
  const remaining = duration ? Math.max(0, duration - elapsed) : null

  return (
    <div className="absolute bottom-0 left-0 right-0 bg-black/70 px-3 pb-2 pt-1 font-sans">
      {/* Progress bar */}
      <div className="mb-1.5 h-1 w-full rounded bg-white/20">
        <div
          className="h-1 rounded bg-red-500 transition-all duration-1000"
          style={{ width: `${progress * 100}%` }}
        />
      </div>

      {/* Title + requester row */}
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-medium text-white">
          ♪ {entry.title || entry.video_id}
        </span>
        <span className="shrink-0 text-xs text-white/50">by {entry.requested_by}</span>
      </div>

      {/* Remaining + queue info row */}
      <div className="mt-0.5 flex items-center justify-between text-[11px] text-white/40">
        <span>{remaining !== null ? `剩餘 ${formatSeconds(remaining)}` : ''}</span>
        {queueCount > 0 && (
          <span>
            待播 {queueCount} 部
            {totalQueuedDuration ? `（共 ${formatSeconds(totalQueuedDuration)}）` : ''}
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main Overlay
// ---------------------------------------------------------------------------

export default function VideoQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const [state, setState] = useState<PublicVideoQueueState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [ytReady, setYtReady] = useState(false)
  const [showClickPrompt, setShowClickPrompt] = useState(false)

  const playerRef = useRef<YTPlayer | null>(null)
  // containerRef: stable React-managed div (empty in vdom, children managed imperatively)
  const containerRef = useRef<HTMLDivElement>(null)
  const currentIdRef = useRef<number | null>(null)
  const advancingRef = useRef(false) // prevent concurrent advance calls
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useDocumentTitle('Video Queue Overlay')

  // Load YouTube IFrame API once
  useEffect(() => {
    loadYouTubeAPI().then(() => setYtReady(true))
  }, [])

  // Poll state every 5s
  useEffect(() => {
    if (!username) return

    const fetchState = async () => {
      try {
        const data = await getPublicVideoQueueState(username)
        setState(data)
      } catch {
        // silent on transient network errors
      }
    }

    fetchState()
    pollRef.current = setInterval(fetchState, POLL_INTERVAL)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [username])

  // Auto-kickstart: if there is no current video but there is a queue, advance
  useEffect(() => {
    if (!username || !state) return
    if (state.current === null && state.queue.length > 0 && !advancingRef.current) {
      advancingRef.current = true
      advanceVideoQueue(username, null)
        .then(newState => setState(newState))
        .catch(() => {})
        .finally(() => {
          advancingRef.current = false
        })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, state?.current?.id, state?.queue.length])

  // Create / destroy YouTube player when current video changes
  useEffect(() => {
    if (!ytReady || !containerRef.current) return

    const current = state?.current ?? null
    const newId = current?.id ?? null

    if (newId === currentIdRef.current) return // same video, nothing to do

    // Destroy old player
    if (playerRef.current) {
      try {
        playerRef.current.destroy()
      } catch {
        /* ignore */
      }
      playerRef.current = null
    }
    if (progressRef.current) {
      clearInterval(progressRef.current)
      progressRef.current = null
    }
    setElapsed(0)

    currentIdRef.current = newId

    if (!current || !newId) return // queue is empty, stay transparent

    // Create new player — pass an imperative child div so YT.Player's
    // parentNode.replaceChild() never detaches containerRef from the DOM
    const mountDiv = document.createElement('div')
    mountDiv.style.cssText = 'width:100%;height:100%'
    containerRef.current.innerHTML = ''
    containerRef.current.appendChild(mountDiv)
    playerRef.current = new window.YT.Player(mountDiv, {
      width: '100%',
      height: '100%',
      videoId: current.video_id,
      playerVars: { autoplay: 1, controls: 0, rel: 0, modestbranding: 1 },
      events: {
        onReady: event => {
          const duration = event.target.getDuration()
          // Report duration to backend (fallback for entries where API returned null)
          if (duration > 0 && !current.duration_seconds && username) {
            reportVideoMetadata(username, current.id, Math.round(duration)).catch(() => {})
          }
          event.target.playVideo()
          setShowClickPrompt(false)

          // Start 1s progress interval
          progressRef.current = setInterval(() => {
            if (!playerRef.current) return
            const t = playerRef.current.getCurrentTime()
            setElapsed(t)

            // ENDED fallback: polling check to catch missed onStateChange ENDED events
            const d = playerRef.current.getDuration()
            if (d > 0 && t >= d - 0.5) {
              handleVideoEnd(current.id)
            }
          }, 1000)
        },

        onStateChange: event => {
          if (event.data === 0) {
            // YT.PlayerState.ENDED = 0
            handleVideoEnd(current.id)
          }
        },

        onError: () => {
          // Skip unplayable / region-locked videos
          handleVideoEnd(current.id)
        },

        onAutoplayBlocked: () => {
          // OBS never hits this; shown only in regular browser testing
          setShowClickPrompt(true)
        },
      },
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ytReady, state?.current?.id, username])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (playerRef.current) {
        try {
          playerRef.current.destroy()
        } catch {
          /* ignore */
        }
      }
      if (progressRef.current) clearInterval(progressRef.current)
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  function handleVideoEnd(doneId: number) {
    if (advancingRef.current) return
    advancingRef.current = true

    if (progressRef.current) {
      clearInterval(progressRef.current)
      progressRef.current = null
    }

    if (!username) return
    advanceVideoQueue(username, doneId)
      .then(newState => setState(newState))
      .catch(() => {})
      .finally(() => {
        advancingRef.current = false
      })
  }

  if (!username) return null

  const current = state?.current ?? null
  const queueCount = state?.queue_size ?? 0
  const totalQueuedDuration = state?.total_queued_duration ?? null

  // Empty queue and no current → fully transparent (OBS sees nothing)
  if (!current && queueCount === 0) return null

  return (
    <div className="relative h-screen w-screen overflow-hidden bg-black font-sans">
      {/* YouTube player fills the entire browser source */}
      <div ref={containerRef} className="h-full w-full" />

      {/* Info overlay (only shown when a video is playing) */}
      {current && (
        <InfoBar
          entry={current}
          elapsed={elapsed}
          queueCount={queueCount}
          totalQueuedDuration={totalQueuedDuration}
        />
      )}

      {/* Autoplay-blocked prompt (browser testing only; OBS never shows this) */}
      {showClickPrompt && (
        <div
          className="absolute inset-0 flex cursor-pointer items-center justify-center bg-black/60"
          onClick={() => {
            playerRef.current?.playVideo()
            setShowClickPrompt(false)
          }}
        >
          <span className="text-2xl text-white">▶ 點擊開始播放</span>
        </div>
      )}
    </div>
  )
}
