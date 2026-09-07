import { type Dispatch, type SetStateAction, useEffect, useState } from 'react'

import {
  openVideoQueueStream,
  type VideoQueueStreamMessage,
  type VideoQueueStreamState,
} from '@/api/videoQueueStream'

// A stream that survives this long resets the reconnect backoff — mirrors
// VideoQueueOverlay.tsx / CommunityOverlay.tsx so a flapping connection still
// escalates its delay instead of reconnecting every second.
const STABLE_STREAM_MS = 30_000

interface UseVideoQueueStreamResult {
  /** Latest queue snapshot, or null before the first frame arrives. */
  state: VideoQueueStreamState | null
  /**
   * Setter for optimistic local updates after a mutation (skip / clear / …).
   * The next stream frame — pushed within milliseconds by the DB NOTIFY
   * trigger — reconciles it, so this only bridges the round-trip gap.
   */
  setState: Dispatch<SetStateAction<VideoQueueStreamState | null>>
}

/**
 * Subscribe the dashboard to the same NOTIFY-woken SSE stream the OBS overlay
 * uses, replacing fixed-interval polling. Reconnect/backoff mirrors
 * VideoQueueOverlay.tsx: a stream alive past STABLE_STREAM_MS resets the
 * attempt counter; otherwise jittered exponential up to 30s.
 *
 * The stream payload is deliberately narrower than the REST state (no
 * `enabled`) — callers read that from the one-shot settings fetch.
 */
export function useVideoQueueStream(username: string | undefined): UseVideoQueueStreamResult {
  const [state, setState] = useState<VideoQueueStreamState | null>(null)

  useEffect(() => {
    // No username (signed out / not an affiliate): nothing to subscribe to.
    // Any stale snapshot sits behind the page's own gate until unmount.
    if (!username) return
    let active = true
    let attempt = 0
    let controller: AbortController | null = null
    let reconnectTimer: number | null = null

    const onMessage = (message: VideoQueueStreamMessage) => {
      if (active) setState(message)
    }

    const connect = () => {
      controller = new AbortController()
      const connectedAt = Date.now()
      void openVideoQueueStream({ username, signal: controller.signal, onMessage })
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

  return { state, setState }
}
