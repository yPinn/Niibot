import { type Dispatch, type SetStateAction, useCallback, useState } from 'react'

import { openVideoQueueStream, type VideoQueueStreamState } from '@/api/videoQueueStream'
import {
  type StreamHelpers,
  type StreamStatus,
  useReconnectingStream,
} from '@/hooks/useReconnectingStream'

interface UseVideoQueueStreamResult {
  /** Latest queue snapshot, or null before the first frame arrives. */
  state: VideoQueueStreamState | null
  /**
   * Setter for optimistic local updates after a mutation (skip / clear / …).
   * The next stream frame — pushed within milliseconds by the DB NOTIFY
   * trigger — reconciles it, so this only bridges the round-trip gap.
   */
  setState: Dispatch<SetStateAction<VideoQueueStreamState | null>>
  /** 'reconnecting' once the connection has been down past the grace window
   * — drive a stale-data indicator off this rather than off `state` alone. */
  status: StreamStatus
}

/**
 * Subscribe the dashboard to the same NOTIFY-woken SSE stream the OBS overlay
 * uses, replacing fixed-interval polling. Reconnect/backoff/status tracking
 * lives in useReconnectingStream, shared with VideoQueueOverlay.tsx.
 *
 * The stream payload is deliberately narrower than the REST state (no
 * `enabled`) — callers read that from the one-shot settings fetch.
 */
export function useVideoQueueStream(username: string | undefined): UseVideoQueueStreamResult {
  const [state, setState] = useState<VideoQueueStreamState | null>(null)

  const connect = useCallback(
    (signal: AbortSignal, { notifyLive, notifyStreamError }: StreamHelpers) => {
      if (!username) return Promise.resolve()
      return openVideoQueueStream({
        username,
        signal,
        onMessage: message => {
          notifyLive()
          setState(message)
        },
        onStreamError: () => notifyStreamError(),
      })
    },
    [username]
  )

  const { status } = useReconnectingStream({
    // No username (signed out / not an affiliate): nothing to subscribe to.
    // Any stale snapshot sits behind the page's own gate until unmount.
    enabled: !!username,
    label: 'video-queue-stream',
    connect,
  })

  return { state, setState, status }
}
