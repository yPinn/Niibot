import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import {
  advanceVideoQueue,
  getPublicVideoQueueState,
  type PublicVideoQueueState,
  reportVideoMetadata,
} from '@/api/videoQueue'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'

import styles from './VideoQueueOverlay.module.css'

// ---------------------------------------------------------------------------
// YouTube IFrame API — minimal inline types
// ---------------------------------------------------------------------------

interface YTPlayer {
  playVideo(): void
  destroy(): void
  getCurrentTime(): number
  getDuration(): number
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
    mute?: 0 | 1
    iv_load_policy?: 1 | 3
  }
  events?: {
    onReady?: (event: { target: YTPlayer }) => void
    onStateChange?: (event: { target: YTPlayer; data: number }) => void
    onError?: (event: { target: YTPlayer }) => void
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

function formatRemaining(elapsed: number, duration: number | null): string {
  if (!duration) return '--:--'
  const remaining = Math.max(0, duration - elapsed)
  const m = Math.floor(remaining / 60)
  const s = Math.floor(remaining % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

// ---------------------------------------------------------------------------
// Main Overlay
// ---------------------------------------------------------------------------

export default function VideoQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const [searchParams] = useSearchParams()
  const isPreview = searchParams.get('preview') === '1'
  const [state, setState] = useState<PublicVideoQueueState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [ytReady, setYtReady] = useState(false)
  const [isExiting, setIsExiting] = useState(false)

  const playerRef = useRef<YTPlayer | null>(null)
  // containerRef: stable React-managed div (empty in vdom, children managed imperatively)
  const containerRef = useRef<HTMLDivElement>(null)
  const currentIdRef = useRef<number | null>(null)
  const advancingRef = useRef(false) // prevent concurrent advance calls
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const usernameRef = useRef(username)
  useEffect(() => {
    usernameRef.current = username
  }, [username])

  useDocumentTitle('Video Queue Overlay')

  // Load YouTube IFrame API once
  useEffect(() => {
    loadYouTubeAPI().then(() => setYtReady(true))
  }, [])

  const fetchState = useCallback(async () => {
    if (!username) return
    try {
      const data = await getPublicVideoQueueState(username)
      setState(data)
    } catch {
      // silent on transient network errors
    }
  }, [username])

  // Poll state every 5s
  usePolling({ fetchFn: fetchState, intervalMs: POLL_INTERVAL, enabled: !!username })

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
      playerVars: {
        autoplay: 1,
        controls: 0,
        rel: 0,
        modestbranding: 1,
        iv_load_policy: 3,
        mute: isPreview ? 1 : 0,
      },
      events: {
        onReady: event => {
          const duration = event.target.getDuration()
          // Report duration to backend (fallback for entries where API returned null)
          if (duration > 0 && !current.duration_seconds && username) {
            reportVideoMetadata(username, current.id, Math.round(duration)).catch(() => {})
          }
          event.target.playVideo()

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
          handleVideoEnd(current.id)
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
    }
  }, [])

  function handleVideoEnd(doneId: number) {
    if (advancingRef.current || !usernameRef.current) return
    advancingRef.current = true

    if (progressRef.current) {
      clearInterval(progressRef.current)
      progressRef.current = null
    }

    setIsExiting(true)
    setTimeout(() => {
      advanceVideoQueue(usernameRef.current!, doneId)
        .then(newState => {
          setState(newState)
          setIsExiting(false)
        })
        .catch(() => {
          setIsExiting(false)
        })
        .finally(() => {
          advancingRef.current = false
        })
    }, 600)
  }

  if (!username) return null

  const current = state?.current ?? null
  const queueCount = state?.queue_size ?? 0
  const progress =
    current?.duration_seconds && current.duration_seconds > 0
      ? Math.min(elapsed / current.duration_seconds, 1)
      : 0

  // Empty queue and no current → fully transparent (OBS sees nothing)
  if (!current && queueCount === 0) return null

  return (
    <div
      className={`${styles.overlay}${isExiting ? ` ${styles.overlayExiting}` : ''}`}
      style={isPreview ? { width: '100%', height: '100dvh' } : undefined}
    >
      {current && (
        <div key={current.id} className={styles.titleBar}>
          <div className={styles.titleLeft}>
            <span className={styles.titleName}>@ {current.requested_by}</span>
          </div>
          <div className={styles.controls}>
            {Array.from(formatRemaining(elapsed, current.duration_seconds)).map((char, i) => (
              <div
                key={i}
                className={char === ':' || char === '-' ? styles.charBoxNarrow : styles.charBox}
              >
                {char}
              </div>
            ))}
          </div>
        </div>
      )}
      <div className={styles.videoPanel}>
        {current && (
          <div className={styles.progressBar}>
            <div className={styles.progressFill} style={{ width: `${progress * 100}%` }} />
          </div>
        )}
        <div ref={containerRef} className={styles.videoContainer} />
        <div className={styles.sunkenOverlay} />
      </div>
    </div>
  )
}
