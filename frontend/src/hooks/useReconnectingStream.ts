import { useCallback, useEffect, useRef, useState } from 'react'

import { reportSilent } from '@/lib/clientErrorReporter'

// A stream that survives this long resets the reconnect backoff, so a
// flapping connection still escalates its delay instead of reconnecting
// every second.
const STABLE_STREAM_MS = 30_000

// The server renews these streams' lease every few minutes by cleanly ending
// the response, which reconnects almost instantly (<1s) — that routine gap
// must not flip the UI into "reconnecting". Only a gap that outlasts this
// grace window is a real disconnect worth showing.
const RECONNECT_GRACE_MS = 3_000

export type StreamStatus = 'connecting' | 'live' | 'reconnecting'

export interface StreamHelpers {
  /** Call from the stream's onMessage — any frame proves the connection is live. */
  notifyLive: () => void
  /** Call when the server sends an explicit `stream_error` frame — an
   * unambiguous real failure, reported immediately rather than inferred
   * from a connection gap. */
  notifyStreamError: (detail?: string) => void
}

export interface UseReconnectingStreamOptions {
  enabled: boolean
  /** Label used for error-report context, e.g. 'video-queue-stream'. */
  label: string
  /** Opens one connection attempt; resolves when the server ends the stream
   * (routine lease renewal or after reporting a failure via
   * notifyStreamError), rejects on a genuine client-side failure (network,
   * bad response). Memoize with useCallback — this is an effect dependency. */
  connect: (signal: AbortSignal, helpers: StreamHelpers) => Promise<void>
}

/**
 * Shared connect/backoff loop for the NOTIFY-woken SSE streams (Video Queue,
 * Live Display). Consolidates what used to be three near-identical
 * implementations and adds connection-status tracking on top, so a
 * genuinely stale stream can be surfaced to a human instead of failing
 * silently.
 */
export function useReconnectingStream({ enabled, label, connect }: UseReconnectingStreamOptions): {
  status: StreamStatus
} {
  const [status, setStatus] = useState<StreamStatus>('connecting')
  const graceTimerRef = useRef<number | null>(null)
  const everLiveRef = useRef(false)

  const notifyLive = useCallback(() => {
    everLiveRef.current = true
    if (graceTimerRef.current !== null) {
      window.clearTimeout(graceTimerRef.current)
      graceTimerRef.current = null
    }
    setStatus('live')
  }, [])

  const notifyStreamError = useCallback(
    (detail?: string) => {
      reportSilent(new Error(`${label} stream error${detail ? `: ${detail}` : ''}`))
    },
    [label]
  )

  useEffect(() => {
    if (!enabled) return

    let active = true
    let attempt = 0
    let controller: AbortController | null = null
    let reconnectTimer: number | null = null

    const run = () => {
      controller = new AbortController()
      const connectedAt = Date.now()

      graceTimerRef.current = window.setTimeout(() => {
        graceTimerRef.current = null
        if (active) setStatus(everLiveRef.current ? 'reconnecting' : 'connecting')
      }, RECONNECT_GRACE_MS)

      void connect(controller.signal, { notifyLive, notifyStreamError })
        .catch(err => {
          if (active && !controller?.signal.aborted) reportSilent(err)
        })
        .finally(() => {
          if (graceTimerRef.current !== null) {
            window.clearTimeout(graceTimerRef.current)
            graceTimerRef.current = null
          }
          if (!active || controller?.signal.aborted) return
          if (Date.now() - connectedAt >= STABLE_STREAM_MS) attempt = 0
          const base = Math.min(1_000 * 2 ** attempt, 30_000)
          const delay = Math.round(base * (0.8 + Math.random() * 0.4))
          attempt += 1
          reconnectTimer = window.setTimeout(run, delay)
        })
    }

    run()
    return () => {
      active = false
      everLiveRef.current = false
      controller?.abort()
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
      if (graceTimerRef.current !== null) {
        window.clearTimeout(graceTimerRef.current)
        graceTimerRef.current = null
      }
    }
  }, [enabled, connect, notifyLive, notifyStreamError])

  // Computed, not stored — avoids a setState call whose only purpose would
  // be mirroring `enabled`, which React's effect linter flags as an
  // anti-pattern (derive-in-render is the equivalent it wants instead).
  return { status: enabled ? status : 'connecting' }
}
