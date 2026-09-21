import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useSearchParams } from 'react-router-dom'

import {
  advanceVideoQueue,
  getPublicVideoQueueState,
  reportPlaybackStarted,
} from '@/api/videoQueue'
import { openVideoQueueStream, type VideoQueueStreamState } from '@/api/videoQueueStream'
import { OverlayReconnectingBadge } from '@/components/OverlayReconnectingBadge'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { type StreamHelpers, useReconnectingStream } from '@/hooks/useReconnectingStream'

import {
  destroyAllPlayers,
  getPlayerStrategy,
  loadTwitchEmbedAPI,
  loadYouTubeAPI,
  type YTPlayer,
} from './videoQueueOverlay/players'

import styles from './VideoQueueOverlay.module.css'

// Bounds how many recently-finished video ids we remember to reject stale
// frames — see the race-protection note on advancedIdsRef below.
const MAX_REMEMBERED_ADVANCED_IDS = 50
const ADVANCE_RETRY_MS = 2_000
const PLAYBACK_START_TIMEOUT_MS = 15_000

function formatRemaining(elapsed: number, duration: number | null): string {
  if (!duration) return '--:--'
  const remaining = Math.max(0, duration - elapsed)
  const m = Math.floor(remaining / 60)
  const s = Math.floor(remaining % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function VideoQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const isPreview = searchParams.get('preview') === '1'
  const overlayKey = new URLSearchParams(location.hash.slice(1)).get('key')
  const [state, setState] = useState<VideoQueueStreamState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [ytReady, setYtReady] = useState(false)
  const [twitchReady, setTwitchReady] = useState(false)
  const [volumePercent, setVolumePercent] = useState(100)
  const [isExiting, setIsExiting] = useState(false)
  const currentVideoType = state?.current?.video_type

  const playerRef = useRef<YTPlayer | null>(null)
  const leftPlayerRef = useRef<YTPlayer | null>(null)
  const rightPlayerRef = useRef<YTPlayer | null>(null)
  // containerRef: stable React-managed div (empty in vdom, children managed imperatively)
  const containerRef = useRef<HTMLDivElement>(null)
  const leftContainerRef = useRef<HTMLDivElement>(null)
  const rightContainerRef = useRef<HTMLDivElement>(null)
  const currentIdRef = useRef<number | null>(null)
  const mountedVolumeRef = useRef<number | null>(null)
  const advancingRef = useRef(false) // prevent concurrent advance calls
  // Video ids this client has already locally advanced past. A stream frame
  // whose `current.id` is in this set is stale (in flight from before the
  // advance committed) and must be rejected instead of reverting the player
  // to a video that already finished. See handleVideoEnd.
  const advancedIdsRef = useRef<Set<number>>(new Set())
  const progressRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const clipTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const kickstartRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const advanceRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const playbackStartTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const reportedPlaybackRef = useRef<{
    entryId: number | null
    signal: 'confirmed' | 'best_effort' | null
  }>({ entryId: null, signal: null })
  const usernameRef = useRef(username)
  const overlayKeyRef = useRef(overlayKey)
  const isPreviewRef = useRef(isPreview)
  const mountedRef = useRef(true)
  useEffect(() => {
    usernameRef.current = username
    overlayKeyRef.current = overlayKey
    isPreviewRef.current = isPreview
  }, [username, overlayKey, isPreview])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
    }
  }, [])

  useDocumentTitle('Video Queue Overlay')

  // Fetch the read-only playback configuration separately from the SSE queue
  // snapshot. A late response remounts the current player once with the right gain.
  useEffect(() => {
    if (!username) return
    let cancelled = false
    void getPublicVideoQueueState(username)
      .then(publicState => {
        if (!cancelled) setVolumePercent(Math.min(100, Math.max(0, publicState.volume_percent)))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [username])

  // Load the YouTube IFrame API only when the current provider needs it.
  useEffect(() => {
    if (currentVideoType !== 'youtube') return
    loadYouTubeAPI()
      .then(() => {
        if (mountedRef.current) setYtReady(true)
      })
      .catch(() => {}) // onerror resets _ytReadyPromise for retry on next mount
  }, [currentVideoType])

  // Load the Twitch embed API only for VOD entries. Clips use a direct video
  // or iframe path and do not need this SDK.
  useEffect(() => {
    if (currentVideoType !== 'twitch_vod') return
    loadTwitchEmbedAPI()
      .then(() => {
        if (mountedRef.current) setTwitchReady(true)
      })
      .catch(() => {})
  }, [currentVideoType])

  // NOTIFY-woken SSE stream, replacing the old fixed-interval poll. No
  // cursor: video queue state is a single current snapshot, not an event
  // log. Reconnect/backoff/status tracking lives in useReconnectingStream,
  // shared with the dashboard's useVideoQueueStream.
  const connect = useCallback(
    (signal: AbortSignal, { notifyLive, notifyStreamError }: StreamHelpers) => {
      if (!username) return Promise.resolve()
      return openVideoQueueStream({
        username,
        signal,
        onMessage: message => {
          notifyLive()
          if (!mountedRef.current) return
          if (message.current && advancedIdsRef.current.has(message.current.id)) return
          setState(message)
        },
        onStreamError: () => notifyStreamError(),
      })
    },
    [username]
  )

  const { status: streamStatus } = useReconnectingStream({
    enabled: !!username,
    label: 'video-queue-overlay-stream',
    connect,
  })

  // Auto-kickstart: if there is no current video but there is a queue, advance
  useEffect(() => {
    if (!username || !overlayKey || !state || isPreview) return
    if (state.current === null && state.queue.length > 0 && !advancingRef.current) {
      advancingRef.current = true
      let cancelled = false
      const requestKickstart = (): void => {
        if (cancelled || !mountedRef.current) {
          advancingRef.current = false
          return
        }
        advanceVideoQueue(username, null, overlayKey)
          .then(newState => {
            if (cancelled || !mountedRef.current) return
            setVolumePercent(newState.volume_percent)
            setState(newState)
            advancingRef.current = false
          })
          .catch(() => {
            if (cancelled || !mountedRef.current) {
              advancingRef.current = false
              return
            }
            kickstartRetryTimerRef.current = setTimeout(requestKickstart, ADVANCE_RETRY_MS)
          })
      }
      requestKickstart()
      return () => {
        cancelled = true
        if (kickstartRetryTimerRef.current) {
          clearTimeout(kickstartRetryTimerRef.current)
          kickstartRetryTimerRef.current = null
        }
        advancingRef.current = false
      }
    }
    // Only react to specific state fields — not the full `state` object —
    // to avoid re-running the advance logic on unrelated state updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, overlayKey, isPreview, state?.current?.id, state?.queue.length])

  // useCallback with empty deps: all reads are via refs (stable identity), setState/setIsExiting
  // are stable React dispatch functions — no stale closure risk from future refactors.
  const handleVideoEnd = useCallback(
    (
      doneId: number,
      reason: 'completed' | 'provider_error' | 'autoplay_blocked' | 'startup_timeout' = 'completed'
    ) => {
      if (
        isPreviewRef.current ||
        advancingRef.current ||
        !usernameRef.current ||
        !overlayKeyRef.current
      )
        return
      advancingRef.current = true
      if (playbackStartTimerRef.current) {
        clearTimeout(playbackStartTimerRef.current)
        playbackStartTimerRef.current = null
      }

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
      const requestAdvance = (): void => {
        if (!mountedRef.current || !usernameRef.current || !overlayKeyRef.current) {
          advancingRef.current = false
          return
        }
        const advanceRequest =
          reason === 'completed'
            ? advanceVideoQueue(usernameRef.current, doneId, overlayKeyRef.current)
            : advanceVideoQueue(usernameRef.current, doneId, overlayKeyRef.current, reason)
        advanceRequest
          .then(newState => {
            if (!mountedRef.current) return
            setVolumePercent(newState.volume_percent)
            setState(newState)
            setIsExiting(false)
            advancingRef.current = false
          })
          .catch(() => {
            if (!mountedRef.current) return
            advanceRetryTimerRef.current = setTimeout(requestAdvance, ADVANCE_RETRY_MS)
          })
      }
      advanceRetryTimerRef.current = setTimeout(requestAdvance, 600)
    },
    []
  )

  // Create / destroy player(s) when current video changes
  useEffect(() => {
    if (!containerRef.current) return

    const current = state?.current ?? null
    const newId = current?.id ?? null

    if (newId === currentIdRef.current && volumePercent === mountedVolumeRef.current) return

    const strategy = current ? getPlayerStrategy(current.video_type) : undefined

    if (playbackStartTimerRef.current) {
      clearTimeout(playbackStartTimerRef.current)
      playbackStartTimerRef.current = null
    }
    if (current && strategy && !isPreview && overlayKey) {
      playbackStartTimerRef.current = setTimeout(
        () => handleVideoEnd(current.id, 'startup_timeout'),
        PLAYBACK_START_TIMEOUT_MS
      )
    }

    // YouTube and Twitch VOD each need an external player API ready before they
    // can mount; the Twitch clip and Bilibili strategies are plain iframes.
    if (strategy?.requiresApi === 'youtube' && !ytReady) return
    if (strategy?.requiresApi === 'twitch' && !twitchReady) return

    destroyAllPlayers(
      [playerRef, leftPlayerRef, rightPlayerRef],
      progressRef,
      clipTimerRef,
      playbackStartTimerRef,
      containerRef,
      setElapsed,
      [leftContainerRef, rightContainerRef]
    )
    currentIdRef.current = newId
    mountedVolumeRef.current = volumePercent
    if (reportedPlaybackRef.current.entryId !== newId) {
      reportedPlaybackRef.current = { entryId: newId, signal: null }
    }

    if (current && strategy && !isPreview && overlayKey) {
      playbackStartTimerRef.current = setTimeout(
        () => handleVideoEnd(current.id, 'startup_timeout'),
        PLAYBACK_START_TIMEOUT_MS
      )
    }

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
      overlayKey,
      muted: isPreview,
      volumePercent,
      username,
      containerRef,
      leftContainerRef,
      rightContainerRef,
      playerRef,
      leftPlayerRef,
      rightPlayerRef,
      progressRef,
      clipTimerRef,
      playbackStartTimerRef,
      currentIdRef,
      setElapsed,
      notifyPlaybackStarted: (signal = 'confirmed') => {
        if (playbackStartTimerRef.current) {
          clearTimeout(playbackStartTimerRef.current)
          playbackStartTimerRef.current = null
        }
        if (isPreview || !username || !overlayKey) return
        const previous = reportedPlaybackRef.current
        if (
          previous.entryId === current.id &&
          (previous.signal === 'confirmed' || previous.signal === signal)
        )
          return
        reportedPlaybackRef.current = { entryId: current.id, signal }
        reportPlaybackStarted(username, current.id, signal, overlayKey).catch(() => {})
      },
      handleVideoEnd,
    })
    // Player creation is keyed on video ID — not the full `state` object or `isPreview` —
    // so the player is only rebuilt when the actual video changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ytReady, twitchReady, state?.current?.id, username, handleVideoEnd, volumePercent])

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
      if (kickstartRetryTimerRef.current) clearTimeout(kickstartRetryTimerRef.current)
      if (advanceRetryTimerRef.current) clearTimeout(advanceRetryTimerRef.current)
      if (playbackStartTimerRef.current) clearTimeout(playbackStartTimerRef.current)
    }
  }, [])

  if (!username) return null

  const current = state?.current ?? null
  const queueCount = state?.queue_size ?? 0
  const progress =
    current?.duration_seconds && current.duration_seconds > 0
      ? Math.min(elapsed / current.duration_seconds, 1)
      : 0

  // Empty queue and no current → fully transparent (OBS sees nothing), except
  // in preview mode a streamer testing connectivity should still see the
  // reconnecting indicator even with nothing queued.
  if (!current && queueCount === 0) {
    return <OverlayReconnectingBadge visible={isPreview && streamStatus === 'reconnecting'} />
  }

  return (
    <div
      className={`${styles.overlay}${isExiting ? ` ${styles.overlayExiting}` : ''}`}
      style={isPreview ? { width: '100%', height: '100dvh' } : undefined}
    >
      <OverlayReconnectingBadge visible={isPreview && streamStatus === 'reconnecting'} />
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
