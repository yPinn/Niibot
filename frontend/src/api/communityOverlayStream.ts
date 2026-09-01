import type {
  CommunityOverlayContentType,
  CommunityOverlayEvent,
  CommunityOverlayPublishedTheme,
} from './communityOverlay'
import { API_ENDPOINTS } from './config'

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

export class CommunityOverlaySseParser {
  private buffer = ''
  private readonly onMessage: (message: CommunityOverlayStreamMessage) => void

  constructor(onMessage: (message: CommunityOverlayStreamMessage) => void) {
    this.onMessage = onMessage
  }

  push(chunk: string): void {
    this.buffer += chunk.replaceAll('\r\n', '\n')
    let boundary = this.buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = this.buffer.slice(0, boundary)
      this.buffer = this.buffer.slice(boundary + 2)
      this.parseFrame(frame)
      boundary = this.buffer.indexOf('\n\n')
    }
  }

  private parseFrame(frame: string): void {
    let eventName = ''
    const data: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (eventName !== 'snapshot' && eventName !== 'update') return
    try {
      const parsed = JSON.parse(data.join('\n')) as unknown
      const withType = { ...(parsed as object), type: eventName }
      if (isStreamMessage(withType)) this.onMessage(withType)
    } catch {
      // A malformed frame is isolated; the following valid frame remains usable.
    }
  }
}

interface OpenStreamOptions {
  publicKey: string
  afterId?: number
  signal: AbortSignal
  onMessage: (message: CommunityOverlayStreamMessage) => void
  fetchImpl?: typeof fetch
}

export async function openCommunityOverlayStream({
  publicKey,
  afterId,
  signal,
  onMessage,
  fetchImpl = fetch,
}: OpenStreamOptions): Promise<void> {
  const query = afterId === undefined ? '' : `?after_id=${encodeURIComponent(afterId)}`
  const response = await fetchImpl(`${API_ENDPOINTS.communityOverlay.stream}${query}`, {
    headers: { 'X-Overlay-Key': publicKey },
    signal,
  })
  const contentType = response.headers.get('Content-Type') ?? ''
  if (!response.ok || !contentType.toLowerCase().startsWith('text/event-stream')) {
    throw new Error(`Live Display stream expected text/event-stream, received ${contentType}`)
  }
  if (!response.body) throw new Error('Live Display stream response has no body')

  const parser = new CommunityOverlaySseParser(onMessage)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      parser.push(decoder.decode(value, { stream: true }))
    }
    parser.push(decoder.decode())
  } finally {
    reader.releaseLock()
  }
}
