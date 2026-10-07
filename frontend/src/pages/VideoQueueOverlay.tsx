import { useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useParams, useSearchParams } from 'react-router-dom'

import { ApiError } from '@/api/errors'
import {
  advanceVideoQueue,
  getPublicVideoQueueState,
  liveInsertPlaylistUrl,
  reportLiveInsertEnded,
  reportPlaybackStarted,
} from '@/api/videoQueue'
import { openVideoQueueStream, type VideoQueueStreamState } from '@/api/videoQueueStream'
import { OverlayReconnectingBadge } from '@/components/OverlayReconnectingBadge'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { type StreamHelpers, useReconnectingStream } from '@/hooks/useReconnectingStream'
import { reportClientError } from '@/lib/clientErrorReporter'

import {
  destroyAllPlayers,
  getPlayerStrategy,
  type LiveInsertController,
  loadYouTubeAPI,
  mountLiveInsert,
  type YTPlayer,
} from './videoQueueOverlay/players'

import styles from './VideoQueueOverlay.module.css'

// Bounds how many recently-finished video ids we remember to reject stale
// frames — see the race-protection note on advancedIdsRef below.
const MAX_REMEMBERED_ADVANCED_IDS = 50
const ADVANCE_RETRY_MS = 2_000
const PLAYBACK_START_TIMEOUT_MS = 15_000
// Settings default for new channels (migration 157); used if they can't load.
const DEFAULT_VOLUME_PERCENT = 50
// Matches the overlayExit animation in VideoQueueOverlay.module.css.
const EXIT_ANIMATION_MS = 600

interface OverlayFrame {
  kind: 'queue' | 'live'
  /** Title-bar text; null while a queued item waits to be kickstarted. */
  title: string | null
  audioOnly: boolean
}

function sameFrame(a: OverlayFrame, b: OverlayFrame | null): boolean {
  return !!b && a.kind === b.kind && a.title === b.title && a.audioOnly === b.audioOnly
}

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
  // null until the settings load: queue players wait for it, so nothing plays
  // at a wrong gain and nothing remounts when the real value arrives.
  const [volumePercent, setVolumePercent] = useState<number | null>(null)
  const [isExiting, setIsExiting] = useState(false)
  // The capability in this URL was rotated away (dashboard 重設網址): advancing
  // can never succeed again, so stop asking — retrying every 2s would burn
  // ~43k Cloudflare requests a day — and tell the streamer instead.
  const [keyRejected, setKeyRejected] = useState(false)
  const keyRejectedRef = useRef(false)
  // Live insert (直播播放): while one is active the overlay plays it instead of
  // the queue, and the queue is paused (server-side too). An insert this
  // client saw end is hidden at once, before the stream confirms it is gone.
  const [endedInsertId, setEndedInsertId] = useState<number | null>(null)
  const liveInsert = state?.insert && state.insert.id !== endedInsertId ? state.insert : null
  const insertId = liveInsert?.id ?? null
  const currentVideoType = liveInsert ? undefined : state?.current?.video_type

  // What the window shows; null when there is nothing. The last frame is kept
  // so a disappearing window plays its exit animation with its old title
  // instead of vanishing — stream-driven removals (dashboard skip/clear, an
  // insert ending) never go through handleVideoEnd's exit.
  const frame: OverlayFrame | null = liveInsert
    ? {
        kind: 'live',
        title: liveInsert.creator_name || liveInsert.source_id,
        audioOnly: liveInsert.audio_only,
      }
    : state?.current
      ? { kind: 'queue', title: `@ ${state.current.requested_by}`, audioOnly: false }
      : (state?.queue_size ?? 0) > 0
        ? { kind: 'queue', title: null, audioOnly: false }
        : null
  const [lastFrame, setLastFrame] = useState<OverlayFrame | null>(frame)
  const [leaving, setLeaving] = useState(false)
  // Adjusting state while rendering (React's documented pattern for state
  // derived from a changing input) so the exit starts on this very render.
  if (frame && !sameFrame(frame, lastFrame)) {
    setLastFrame(frame)
    if (leaving) setLeaving(false)
  } else if (!frame && lastFrame && !leaving) {
    setLeaving(true)
  }
  useEffect(() => {
    if (!leaving) return
    const timer = setTimeout(() => {
      setLeaving(false)
      setLastFrame(null)
    }, EXIT_ANIMATION_MS)
    return () => clearTimeout(timer)
  }, [leaving])

  const playerRef = useRef<YTPlayer | null>(null)
  const leftPlayerRef = useRef<YTPlayer | null>(null)
  const rightPlayerRef = useRef<YTPlayer | null>(null)
  // containerRef: stable React-managed div (empty in vdom, children managed imperatively)
  const containerRef = useRef<HTMLDivElement>(null)
  const leftContainerRef = useRef<HTMLDivElement>(null)
  const rightContainerRef = useRef<HTMLDivElement>(null)
  const currentIdRef = useRef<number | null>(null)
  const insertContainerRef = useRef<HTMLDivElement>(null)
  const insertControllerRef = useRef<LiveInsertController | null>(null)
  // Latest insert volume for the async mount below (the API load can resolve
  // after a volume change). Declared before that effect so it runs first.
  const insertVolumeRef = useRef(0)
  useEffect(() => {
    if (liveInsert) insertVolumeRef.current = liveInsert.volume_percent
  })
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
  // snapshot. Players mount once it's known; if it can't be fetched, fall back
  // to the default a fresh channel gets (migration 157).
  useEffect(() => {
    if (!username) return
    let cancelled = false
    void getPublicVideoQueueState(username)
      .then(publicState => {
        if (!cancelled) setVolumePercent(Math.min(100, Math.max(0, publicState.volume_percent)))
      })
      .catch(() => {
        if (!cancelled) setVolumePercent(DEFAULT_VOLUME_PERCENT)
      })
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

  // No Twitch embed preload: VODs play via hls.js and their embed fallback
  // loads Twitch's script itself. A preload here used to flip a `twitchReady`
  // dependency of the player effect right after a VOD mounted — React then ran
  // the effect's cleanup (destroying the fresh player) and the re-run bailed on
  // "same entry", leaving an empty window.

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

  const rejectKey = useCallback((error: unknown): boolean => {
    if (!(error instanceof ApiError) || error.code !== 'VIDEO_QUEUE.OVERLAY_NOT_FOUND') return false
    keyRejectedRef.current = true
    setKeyRejected(true)
    return true
  }, [])

  // Auto-kickstart: if there is no current video but there is a queue, advance
  useEffect(() => {
    if (!username || !overlayKey || !state || isPreview || insertId !== null || keyRejected) return
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
          .catch(error => {
            if (cancelled || !mountedRef.current || rejectKey(error)) {
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
    // state?.insert?.id is the server's view, not just insertId: an insert this
    // overlay already hid locally can still be blocking the server's kickstart.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    username,
    overlayKey,
    isPreview,
    state?.current?.id,
    state?.queue.length,
    insertId,
    state?.insert?.id,
    keyRejected,
  ])

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
        keyRejectedRef.current ||
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
          .catch(error => {
            if (!mountedRef.current) return
            if (rejectKey(error)) {
              setIsExiting(false)
              advancingRef.current = false
              return
            }
            advanceRetryTimerRef.current = setTimeout(requestAdvance, ADVANCE_RETRY_MS)
          })
      }
      advanceRetryTimerRef.current = setTimeout(requestAdvance, 600)
    },
    [rejectKey]
  )

  // Create / destroy player(s) when current video changes
  useEffect(() => {
    if (insertId !== null) {
      // The queue container unmounts for the insert; its player's timers
      // (startup watchdog, progress poll, clip timer) must not keep running
      // and advance the queue behind the insert.
      destroyAllPlayers(
        [playerRef, leftPlayerRef, rightPlayerRef],
        progressRef,
        clipTimerRef,
        playbackStartTimerRef,
        containerRef,
        setElapsed,
        [leftContainerRef, rightContainerRef]
      )
      currentIdRef.current = null
      mountedVolumeRef.current = null
      return
    }
    if (!containerRef.current || volumePercent === null) return

    const current = state?.current ?? null
    const newId = current?.id ?? null

    if (newId === currentIdRef.current && volumePercent === mountedVolumeRef.current) return

    const strategy = current ? getPlayerStrategy(current.video_type) : undefined
    // A player that never starts leaves no other trace (its own retries can
    // outlast the watchdog), so say which platform stalled before skipping.
    const onStartupTimeout = (entry: NonNullable<typeof current>) => {
      reportClientError({
        kind: 'error',
        message: `${entry.video_type}: playback did not start within ${PLAYBACK_START_TIMEOUT_MS / 1000}s`,
        errorCode: 'VIDEO_QUEUE.STARTUP_TIMEOUT',
      })
      handleVideoEnd(entry.id, 'startup_timeout')
    }

    if (playbackStartTimerRef.current) {
      clearTimeout(playbackStartTimerRef.current)
      playbackStartTimerRef.current = null
    }
    if (current && strategy && !isPreview && overlayKey) {
      playbackStartTimerRef.current = setTimeout(
        () => onStartupTimeout(current),
        PLAYBACK_START_TIMEOUT_MS
      )
    }

    // Only YouTube needs an external player API before it can mount; Twitch
    // VOD (its embed script loads itself), clip and Bilibili don't.
    if (strategy?.requiresApi === 'youtube' && !ytReady) return

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
        () => onStartupTimeout(current),
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
  }, [ytReady, state?.current?.id, username, handleVideoEnd, volumePercent, insertId])

  // Mount the live insert's player (keyed on the insert, not its settings).
  useEffect(() => {
    if (!liveInsert) return
    const insert = liveInsert
    let done = false
    // Twitch plays via hls.js and loads its embed fallback itself.
    const load = insert.source_type === 'twitch_live' ? Promise.resolve() : loadYouTubeAPI()
    load
      .then(() => {
        if (done || !insertContainerRef.current) return
        insertControllerRef.current = mountLiveInsert({
          insert: { ...insert, volume_percent: insertVolumeRef.current },
          container: insertContainerRef.current,
          muted: isPreview,
          resolveTwitchSource: username
            ? () => Promise.resolve(liveInsertPlaylistUrl(username))
            : undefined,
          onEnded: reason => {
            if (done) return
            done = true // report once; never retried in a loop
            setEndedInsertId(insert.id)
            if (isPreview || !username || !overlayKey) return
            reportLiveInsertEnded(username, insert.id, reason, overlayKey).catch(() => {})
          },
        })
      })
      .catch(() => {})
    return () => {
      done = true
      insertControllerRef.current?.destroy()
      insertControllerRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [insertId])

  // Volume changes apply to the running insert player without a remount.
  useEffect(() => {
    if (liveInsert) insertControllerRef.current?.setVolume(liveInsert.volume_percent, isPreview)
  }, [liveInsert, isPreview])

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
      insertControllerRef.current?.destroy()
    }
  }, [])

  if (!username) return null

  const current = state?.current ?? null
  const progress =
    current?.duration_seconds && current.duration_seconds > 0
      ? Math.min(elapsed / current.duration_seconds, 1)
      : 0

  // Shown in OBS too: only the streamer can fix it, and a frozen window with no
  // explanation is worse than a short notice.
  if (keyRejected) {
    return <div className={styles.keyNotice}>OBS 網址已失效，請到後台重新加入畫面</div>
  }

  // Nothing to show and nothing leaving → fully transparent (OBS sees nothing),
  // except a preview testing connectivity still sees the reconnecting badge.
  const shown = frame ?? (leaving ? lastFrame : null)
  if (!shown) {
    return <OverlayReconnectingBadge visible={isPreview && streamStatus === 'reconnecting'} />
  }
  // Audio only leaves the same way a finished video does (the exit animation's
  // `forwards` fill keeps it scaled down and transparent while the player
  // keeps playing at its real layout size); turning it off plays the entrance.
  // The dashboard preview skips that and stays faintly visible instead.
  const audioOnlyHidden = shown.audioOnly && !isPreview
  const exiting = isExiting || !frame || audioOnlyHidden
  const isLive = shown.kind === 'live'
  const playing = isLive ? null : current

  // The preview's faint audio-only look sits on a wrapper: an opacity on the
  // animated .overlay itself would lose to the animation's `forwards` fill.
  return (
    <div
      style={{
        ...(isPreview ? { width: '100%', height: '100dvh' } : {}),
        opacity: shown.audioOnly && isPreview ? 0.35 : 1,
      }}
      data-testid={isLive ? 'live-insert' : undefined}
    >
      <div
        key={shown.kind}
        className={`${styles.overlay}${exiting ? ` ${styles.overlayExiting}` : ''}`}
        style={isPreview ? { width: '100%', height: '100%' } : undefined}
      >
        <OverlayReconnectingBadge visible={isPreview && streamStatus === 'reconnecting'} />
        {shown.title !== null && (
          <div key={`${shown.kind}:${playing?.id ?? ''}`} className={styles.titleBar}>
            <div className={styles.titleLeft}>
              <span className={styles.titleName}>{shown.title}</span>
            </div>
            {isLive ? (
              <div className={styles.liveIndicator}>
                <span className={styles.liveDot} aria-hidden="true" />
                LIVE
              </div>
            ) : (
              playing && (
                <div className={styles.controls}>
                  {Array.from(formatRemaining(elapsed, playing.duration_seconds)).map((char, i) => (
                    <div
                      key={i}
                      className={
                        char === ':' || char === '-' ? styles.charBoxNarrow : styles.charBox
                      }
                    >
                      {char}
                    </div>
                  ))}
                </div>
              )
            )}
          </div>
        )}
        {isLive ? (
          <div className={styles.videoPanel}>
            <div ref={insertContainerRef} className={styles.videoContainer} />
            <div className={styles.sunkenOverlay} />
          </div>
        ) : (
          <div className={styles.videoPanel}>
            {playing && (
              <div className={styles.progressBar}>
                <div className={styles.progressFill} style={{ width: `${progress * 100}%` }} />
              </div>
            )}
            <div ref={containerRef} className={styles.videoContainer} />
            {playing?.is_vertical && (
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
        )}
      </div>
    </div>
  )
}
