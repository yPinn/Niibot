import type {
  CommunityOverlayContentType,
  CommunityOverlayEvent,
  CommunityOverlayPublishedTheme,
} from './communityOverlay'
import { API_ENDPOINTS } from './config'
import { openSseStream, type SseFrame, SseFrameParser } from './sseStream'

export interface CommunityOverlayStreamMessage {
  type: 'snapshot' | 'update'
  cursor: number
  events: CommunityOverlayEvent[]
  themes: Partial<Record<CommunityOverlayContentType, CommunityOverlayPublishedTheme>>
}

function isStreamMessage(value: unknown): value is CommunityOverlayStreamMessage {
  if (!value || typeof value !== 'object') return false
  const message = value as Partial<CommunityOverlayStreamMessage>
  return (
    (message.type === 'snapshot' || message.type === 'update') &&
    Number.isInteger(message.cursor) &&
    Array.isArray(message.events) &&
    Boolean(message.themes && typeof message.themes === 'object')
  )
}

function handleFrame(
  frame: SseFrame,
  onMessage: (message: CommunityOverlayStreamMessage) => void,
  onStreamError?: () => void
): void {
  if (frame.event === 'stream_error') {
    onStreamError?.()
    return
  }
  if (frame.event !== 'snapshot' && frame.event !== 'update') return
  try {
    const parsed = JSON.parse(frame.data) as unknown
    const withType = { ...(parsed as object), type: frame.event }
    if (isStreamMessage(withType)) onMessage(withType)
  } catch {
    // A malformed frame is isolated; the following valid frame remains usable.
  }
}

export class CommunityOverlaySseParser {
  private readonly inner: SseFrameParser

  constructor(onMessage: (message: CommunityOverlayStreamMessage) => void) {
    this.inner = new SseFrameParser(frame => handleFrame(frame, onMessage))
  }

  push(chunk: string): void {
    this.inner.push(chunk)
  }
}

interface OpenStreamOptions {
  publicKey: string
  afterId?: number
  signal: AbortSignal
  onMessage: (message: CommunityOverlayStreamMessage) => void
  /** Called when the server reports a genuine mid-stream failure (as opposed
   * to the routine lease-renewal reconnect, which sends nothing). */
  onStreamError?: () => void
  fetchImpl?: typeof fetch
}

export async function openCommunityOverlayStream({
  publicKey,
  afterId,
  signal,
  onMessage,
  onStreamError,
  fetchImpl = fetch,
}: OpenStreamOptions): Promise<void> {
  const query = afterId === undefined ? '' : `?after_id=${encodeURIComponent(afterId)}`
  await openSseStream({
    url: `${API_ENDPOINTS.communityOverlay.stream}${query}`,
    headers: { 'X-Overlay-Key': publicKey },
    signal,
    onFrame: frame => handleFrame(frame, onMessage, onStreamError),
    fetchImpl,
  })
}
