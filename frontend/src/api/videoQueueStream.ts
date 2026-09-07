import { API_ENDPOINTS } from './config'
import { openSseStream, type SseFrame } from './sseStream'
import type { VideoQueueEntry } from './videoQueue'

// Deliberately narrower than PublicVideoQueueState: no `enabled` — see
// VideoQueueStreamState on the backend for why the stream never sends it.
export interface VideoQueueStreamState {
  current: VideoQueueEntry | null
  queue: VideoQueueEntry[]
  queue_size: number
  total_queued_duration: number | null
}

export interface VideoQueueStreamMessage extends VideoQueueStreamState {
  type: 'snapshot' | 'update'
}

function isStreamMessage(value: unknown): value is VideoQueueStreamMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<VideoQueueStreamMessage>
  return (
    (message.type === 'snapshot' || message.type === 'update') &&
    Array.isArray(message.queue) &&
    typeof message.queue_size === 'number'
  )
}

function handleFrame(frame: SseFrame, onMessage: (message: VideoQueueStreamMessage) => void): void {
  // Frames other than snapshot/update (e.g. heartbeat) are intentionally dropped here.
  if (frame.event !== 'snapshot' && frame.event !== 'update') return
  try {
    const parsed = JSON.parse(frame.data) as unknown
    const withType = { ...(parsed as object), type: frame.event }
    if (isStreamMessage(withType)) onMessage(withType)
  } catch {
    // A malformed frame is isolated; the following valid frame remains usable.
  }
}

interface OpenStreamOptions {
  username: string
  signal: AbortSignal
  onMessage: (message: VideoQueueStreamMessage) => void
  fetchImpl?: typeof fetch
}

/** No capability header and no replay cursor — video-queue public endpoints are
 * path-scoped by username (unlike Live Display's header-scoped capability key),
 * and the stream is a single current-state snapshot, not an event log. */
export async function openVideoQueueStream({
  username,
  signal,
  onMessage,
  fetchImpl = fetch,
}: OpenStreamOptions): Promise<void> {
  await openSseStream({
    url: API_ENDPOINTS.videoQueue.stream(username),
    signal,
    onFrame: frame => handleFrame(frame, onMessage),
    fetchImpl,
  })
}
