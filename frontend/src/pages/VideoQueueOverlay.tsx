import { useCallback, useEffect, useRef, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { advanceVideoQueue } from '@/api/videoQueue'
import {
  openVideoQueueStream,
  type VideoQueueStreamMessage,
  type VideoQueueStreamState,
} from '@/api/videoQueueStream'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import {
  destroyAllPlayers,
  getPlayerStrategy,
  loadYouTubeAPI,
  type YTPlayer,
} from './videoQueueOverlay/players'

import styles from './VideoQueueOverlay.module.css'

// A stream that survives this long resets the reconnect backoff — mirrors
// CommunityOverlay.tsx's STABLE_STREAM_MS so a flapping connection still
// escalates its delay instead of hammering the server every second.
const STABLE_STREAM_MS = 30_000

// Bounds how many recently-finished video ids we remember to reject stale
// frames — see the race-protection note on advancedIdsRef below.
const MAX_REMEMBERED_ADVANCED_IDS = 50

function formatRemaining(elapsed: number, duration: number | null): string {
  if (!duration) return '--:--'
  const remaining = Math.max(0, duration - elapsed)
  const m = Math.floor(remaining / 60)
  const s = Math.floor(remaining % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function VideoQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const [searchParams] = useSearchParams()
  const isPreview = searchParams.get('preview') === '1'
  const [state, setState] = useState<VideoQueueStreamState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [ytReady, setYtReady] = useState(false)
  const [isExiting, setIsExiting] = useState(false)

  const playerRef = useRef<YTPlayer | null>(null)
  const leftPlayerRef = useRef<YTPlayer | null>(null)
  const rightPlayerRef = useRef<YTPlayer | null>(null)
  // containerRef: stable React-managed div (empty in vdom, children managed imperatively)
  const containerRef = useRef<HTMLDivElement>(null)
  const leftContainerRef = useRef<HTMLDivElement>(null)
  const rightContainerRef = useRef<HTMLDivElement>(null)
  const currentIdRef = useRef<number | null>(null)
  const advancingRef = useRef(false) // prevent concurrent advance calls
  // Video ids this client has already locally advanced past. A stream frame
  // whose `current.id` is in this set is stale (in flight from before the
  // advance committed) and must be rejected instead of reverting the player
  // to a video that already finished. See handleVideoEnd.
  const advancedIdsRef = useRef<Set<number>>(new Set())
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const clipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const usernameRef = useRef(username)
  const mountedRef = useRef(true)
  useEffect(() => {
    usernameRef.current = username
  }, [username])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useDocumentTitle('Video Queue Overlay')

  // Load YouTube IFrame API once
  useEffect(() => {
    loadYouTubeAPI()
      .then(() => {
        if (mountedRef.current) setYtReady(true)
      })
      .catch(() => {}) // onerror resets _ytReadyPromise for retry on next mount
  }, [])

  // NOTIFY-woken SSE stream, replacing the old fixed-interval poll — see
  // CommunityOverlay.tsx for the reconnect pattern this mirrors. No cursor:
  // video queue state is a single current snapshot, not an event log.
  useEffect(() => {
    if (!username) return
    let active = true
    let attempt = 0
    let controller: AbortController | null = null
    let reconnectTimer: number | null = null

    const applyMessage = (message: VideoQueueStreamMessage) => {
      if (!active) return
      if (message.current && advancedIdsRef.current.has(message.current.id)) return
      setState(message)
    }

    const connect = () => {
      controller = new AbortController()
      const connectedAt = Date.now()
      void openVideoQueueStream({
        username,
        signal: controller.signal,
        onMessage: applyMessage,
      })
        .catch(() => undefined)
        .finally(() => {
          if (!active || controller?.signal.aborted) return
          if (Date.now() - connectedAt >= STABLE_STREAM_MS) attempt = 0
          const base = Math.min(1_000 * 2 ** attempt, 30_000)
          const delay = Math.round(base * (0.8 + Math.random() * 0.4))
          attempt += 1
          reconnectTimer = window.setTimeout(connect, delay)
        })
    }

    connect()
    return () => {
      active = false
      controller?.abort()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
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
    // Only react to specific state fields — not the full `state` object —
    // to avoid re-running the advance logic on unrelated state updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, state?.current?.id, state?.queue.length])

  // useCallback with empty deps: all reads are via refs (stable identity), setState/setIsExiting
  // are stable React dispatch functions — no stale closure risk from future refactors.
  const handleVideoEnd = useCallback((doneId: number) => {
    if (advancingRef.current || !usernameRef.current) return
    advancingRef.current = true

    // Reject any stream frame that still shows doneId as current — it was in
    // flight before this advance committed. The POST response below is
    // read-after-write and always applied directly via setState, bypassing
    // this guard, so it can never be blocked by its own entry.
    advancedIdsRef.current.add(doneId)
    if (advancedIdsRef.current.size > MAX_REMEMBERED_ADVANCED_IDS) {
      advancedIdsRef.current.delete(advancedIdsRef.current.values().next().value as number)
    }

    if (progressRef.current) {
      clearInterval(progressRef.current ?? undefined)
      progressRef.current = null
    }
    if (clipTimerRef.current) {
      clearTimeout(clipTimerRef.current)
      clipTimerRef.current = null
    }

    setIsExiting(true)
    setTimeout(() => {
      advanceVideoQueue(usernameRef.current!, doneId)
        .then(newState => {
          if (!mountedRef.current) return
          setState(newState)
          setIsExiting(false)
        })
        .catch(() => {
          if (!mountedRef.current) return
          setIsExiting(false)
        })
        .finally(() => {
          advancingRef.current = false
        })
    }, 600)
  }, [])

  // Create / destroy player(s) when current video changes
  useEffect(() => {
    if (!containerRef.current) return

    const current = state?.current ?? null
    const newId = current?.id ?? null

    if (newId === currentIdRef.current) return // same video, nothing to do

    const strategy = current ? getPlayerStrategy(current.video_type) : undefined

    // Only YouTube needs an external API (the IFrame API) ready before it can
    // mount — the Twitch clip and Bilibili strategies are plain iframes.
    if (strategy?.requiresApi === 'youtube' && !ytReady) return

    destroyAllPlayers(
      [playerRef, leftPlayerRef, rightPlayerRef],
      progressRef,
      clipTimerRef,
      containerRef,
      setElapsed
    )
    currentIdRef.current = newId

    if (!current || !newId || !strategy) return // queue is empty, stay transparent

    // Compute elapsed seconds since started_at for late-joining overlays
    const joinElapsed = current.started_at
      ? (Date.now() - new Date(current.started_at).getTime()) / 1000
      : 0

    return strategy.mount({
      current,
      currentId: current.id,
      joinElapsed,
      isPreview,
      username,
      containerRef,
      leftContainerRef,
      rightContainerRef,
      playerRef,
      leftPlayerRef,
      rightPlayerRef,
      progressRef,
      clipTimerRef,
      currentIdRef,
      setElapsed,
      handleVideoEnd,
    })
    // Player creation is keyed on video ID — not the full `state` object or `isPreview` —
    // so the player is only rebuilt when the actual video changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ytReady, state?.current?.id, username, handleVideoEnd])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      for (const ref of [playerRef, leftPlayerRef, rightPlayerRef]) {
        if (ref.current) {
          try {
            ref.current.destroy()
          } catch {
            /* ignore */
          }
        }
      }
      if (progressRef.current) clearInterval(progressRef.current ?? undefined)
      if (clipTimerRef.current) clearTimeout(clipTimerRef.current)
    }
  }, [])

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
        {current?.is_vertical && (
          <div className={styles.columnOverlay}>
            <div className={styles.sidePanel}>
              <div ref={leftContainerRef} className={styles.sidePlayerContainer} />
              <div className={styles.sideDarkOverlay} />
            </div>
            <div className={styles.centerPanel} />
            <div className={styles.sidePanel}>
              <div ref={rightContainerRef} className={styles.sidePlayerContainer} />
              <div className={styles.sideDarkOverlay} />
            </div>
          </div>
        )}
        <div className={styles.sunkenOverlay} />
      </div>
    </div>
  )
}
