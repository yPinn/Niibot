// Generic SSE wire-format handling shared by every NOTIFY-woken overlay stream
// (Live Display, Video Queue, ...). Event-name filtering and payload
// validation are feature-specific and stay out of this module — see
// communityOverlayStream.ts and videoQueueStream.ts.

export interface SseFrame {
  event: string
  data: string
}

export class SseFrameParser {
  private buffer = ''
  private readonly onFrame: (frame: SseFrame) => void

  constructor(onFrame: (frame: SseFrame) => void) {
    this.onFrame = onFrame
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
    let event = ''
    const data: string[] = []
    for (const line of frame.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim()
      if (line.startsWith('data:')) data.push(line.slice(5).trimStart())
    }
    if (!event) return
    this.onFrame({ event, data: data.join('\n') })
  }
}

export interface OpenSseStreamOptions {
  url: string
  headers?: Record<string, string>
  signal: AbortSignal
  onFrame: (frame: SseFrame) => void
  fetchImpl?: typeof fetch
}

/**
 * Open one long-lived SSE connection and pump frames to `onFrame` until the
 * server closes the stream, the signal aborts, or the response fails.
 *
 * Rejects unless the response Content-Type starts with `text/event-stream` —
 * this is the anti-fail-open guard against Cloudflare Pages serving the SPA's
 * `index.html` (200 text/html) when a route isn't actually proxied to the
 * backend. Do not remove it when reusing this helper for a new stream.
 */
export async function openSseStream({
  url,
  headers,
  signal,
  onFrame,
  fetchImpl = fetch,
}: OpenSseStreamOptions): Promise<void> {
  const response = await fetchImpl(url, { headers, signal })
  const contentType = response.headers.get('Content-Type') ?? ''
  if (!response.ok || !contentType.toLowerCase().startsWith('text/event-stream')) {
    throw new Error(`SSE stream expected text/event-stream, received ${contentType}`)
  }
  if (!response.body) throw new Error('SSE stream response has no body')

  const parser = new SseFrameParser(onFrame)
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
