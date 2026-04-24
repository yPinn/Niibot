import { type RefObject, useCallback, useEffect, useRef, useState } from 'react'
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

interface YTPlayer {
  playVideo(): void
  pauseVideo(): void
  destroy(): void
  getCurrentTime(): number
  getDuration(): number
  seekTo(seconds: number, allowSeekAhead?: boolean): void
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
    cc_load_policy?: 1 | 3
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

interface TwitchEmbedOptions {
  clip?: string
  channel?: string
  video?: string
  parent: string[]
  layout?: 'video' | 'video-with-chat'
  autoplay?: boolean
  muted?: boolean
  width?: string | number
  height?: string | number
}

interface TwitchEmbedInstance {
  getPlayer(): TwitchPlayerInstance
  addEventListener(event: string, callback: () => void): void
}

interface TwitchPlayerInstance {
  play(): void
  pause(): void
  getMuted(): boolean
  setMuted(muted: boolean): void
}

declare global {
  interface Window {
    Twitch?: {
      Embed: {
        new (container: string | HTMLElement, options: TwitchEmbedOptions): TwitchEmbedInstance
        VIDEO_READY: string
        VIDEO_PLAY: string
      }
      Player?: new (
        element: HTMLElement,
        options: Record<string, unknown>
      ) => { destroy: () => void }
    }
  }
}

let _ytReadyPromise: Promise<void> | null = null

function loadYouTubeAPI(): Promise<void> {
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

let _twitchReadyPromise: Promise<void> | null = null

function loadTwitchEmbedAPI(): Promise<void> {
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

const POLL_INTERVAL = 3_000

function formatRemaining(elapsed: number, duration: number | null): string {
  if (!duration) return '--:--'
  const remaining = Math.max(0, duration - elapsed)
  const m = Math.floor(remaining / 60)
  const s = Math.floor(remaining % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

/** Destroy all active YT players, clear the clip timer, and stop the progress interval. */
function destroyAllPlayers(
  refs: Array<RefObject<YTPlayer | null>>,
  progressRef: RefObject<ReturnType<typeof setInterval> | null>,
  clipTimerRef: RefObject<ReturnType<typeof setTimeout> | null>,
  containerRef: RefObject<HTMLDivElement | null>,
  setElapsed: (v: number) => void
) {
  for (const ref of refs) {
    if (ref.current) {
      try {
        ref.current.destroy()
      } catch {
        /* ignore */
      }
      ref.current = null
    }
  }
  if (progressRef.current) {
    clearInterval(progressRef.current)
    progressRef.current = null
  }
  if (clipTimerRef.current) {
    clearTimeout(clipTimerRef.current)
    clipTimerRef.current = null
  }
  // Clear any iframe left by a Twitch clip player
  if (containerRef.current) {
    containerRef.current.innerHTML = ''
  }
  setElapsed(0)
}

/** Create a fresh full-size mount div inside a container, clearing previous children. */
function makeMountDiv(container: HTMLDivElement): HTMLDivElement {
  const div = document.createElement('div')
  div.style.cssText = 'width:100%;height:100%'
  container.innerHTML = ''
  container.appendChild(div)
  return div
}

export default function VideoQueueOverlay() {
  const { username } = useParams<{ username: string }>()
  const [searchParams] = useSearchParams()
  const isPreview = searchParams.get('preview') === '1'
  const [state, setState] = useState<PublicVideoQueueState | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const [ytReady, setYtReady] = useState(false)
  const [twitchReady, setTwitchReady] = useState(false)
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

  // Load Twitch Embed API once
  useEffect(() => {
    loadTwitchEmbedAPI()
      .then(() => {
        if (mountedRef.current) setTwitchReady(true)
      })
      .catch(() => {})
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

  // Poll state every 3s
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
    // Only react to specific state fields — not the full `state` object —
    // to avoid re-running the advance logic on unrelated state updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [username, state?.current?.id, state?.queue.length])

  // useCallback with empty deps: all reads are via refs (stable identity), setState/setIsExiting
  // are stable React dispatch functions — no stale closure risk from future refactors.
  const handleVideoEnd = useCallback((doneId: number) => {
    if (advancingRef.current || !usernameRef.current) return
    advancingRef.current = true

    if (progressRef.current) {
      clearInterval(progressRef.current)
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

    // YouTube requires the IFrame API to be loaded; Twitch clips need the Twitch Embed API
    if (current?.video_type === 'twitch_clip' && !twitchReady) return
    if (current?.video_type !== 'twitch_clip' && !ytReady) return

    destroyAllPlayers(
      [playerRef, leftPlayerRef, rightPlayerRef],
      progressRef,
      clipTimerRef,
      containerRef,
      setElapsed
    )
    currentIdRef.current = newId

    if (!current || !newId) return // queue is empty, stay transparent

    const currentId = current.id

    // Compute elapsed seconds since started_at for late-joining overlays
    const joinElapsed = current.started_at
      ? (Date.now() - new Date(current.started_at).getTime()) / 1000
      : 0

    // ── Twitch Clip player ──────────────────────────────────────────────
    if (current.video_type === 'twitch_clip') {
      // If the clip has already ended, advance immediately
      if (current.duration_seconds && joinElapsed >= current.duration_seconds - 0.5) {
        handleVideoEnd(currentId)
        return
      }

      // eslint-disable-next-line react-hooks/set-state-in-effect
      setElapsed(joinElapsed) // initialise elapsed for late-joining overlays

      // Start the elapsed counter immediately so the progress UI stays accurate.
      progressRef.current = setInterval(() => {
        setElapsed(prev => prev + 1)
      }, 1000)

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

      // End detection: timer based on remaining clip duration
      if (current.duration_seconds) {
        const remaining = Math.max(0, current.duration_seconds - joinElapsed)
        clipTimerRef.current = setTimeout(() => handleVideoEnd(currentId), remaining * 1000 + 500)
      }
      return // skip YouTube player creation below
    }

    // ── YouTube player ──────────────────────────────────────────────────
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
      if (!current) return // narrowing: current is non-null here by construction

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
        if (d > 0 && t >= d - 0.5) handleVideoEnd(currentId)
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
      containerRefArg: RefObject<HTMLDivElement | null>,
      playerRefArg: RefObject<YTPlayer | null>
    ) {
      if (!containerRefArg.current) {
        onPlayerReady() // container not mounted — count as ready so barrier doesn't stall
        return
      }
      playerRefArg.current = new window.YT.Player(makeMountDiv(containerRefArg.current), {
        width: '100%',
        height: '100%',
        videoId: current!.video_id,
        playerVars: {
          autoplay: 0,
          controls: 0,
          rel: 0,
          modestbranding: 1,
          mute: 1,
          iv_load_policy: 3,
        },
        events: { onReady: onPlayerReady },
      })
    }

    // Center player — pass an imperative child div so YT.Player's
    // parentNode.replaceChild() never detaches containerRef from the DOM
    playerRef.current = new window.YT.Player(makeMountDiv(containerRef.current), {
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
        mute: isPreview ? 1 : 0,
      },
      events: {
        onReady: event => {
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
    // Player creation is keyed on video ID — not the full `state` object or `isPreview` —
    // so the player is only rebuilt when the actual video changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ytReady, twitchReady, state?.current?.id, username, handleVideoEnd])

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
      if (progressRef.current) clearInterval(progressRef.current)
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
