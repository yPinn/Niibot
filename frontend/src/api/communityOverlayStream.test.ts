import { describe, expect, it, vi } from 'vitest'

import { CommunityOverlaySseParser, openCommunityOverlayStream } from './communityOverlayStream'
import { API_ENDPOINTS } from './config'

const KEY = '11111111-1111-4111-8111-111111111111'

describe('CommunityOverlaySseParser', () => {
  it('parses frames split across chunks and ignores malformed JSON', () => {
    const messages: unknown[] = []
    const parser = new CommunityOverlaySseParser(message => messages.push(message))

    parser.push('event: snapshot\ndata: {"cursor":1,"eve')
    parser.push('nts":[],"themes":{}}\n\nevent: update\ndata: nope\n\n')

    expect(messages).toEqual([{ type: 'snapshot', cursor: 1, events: [], themes: {} }])
  })

  it('accepts CRLF frames and skips heartbeat comments', () => {
    const messages: unknown[] = []
    const parser = new CommunityOverlaySseParser(message => messages.push(message))

    parser.push(
      ': keep-alive\r\n\r\nevent: update\r\ndata: {"cursor":2,"events":[],"themes":{}}\r\n\r\n'
    )

    expect(messages).toEqual([{ type: 'update', cursor: 2, events: [], themes: {} }])
  })
})

describe('openCommunityOverlayStream', () => {
  it('uses the capability header, replay cursor, and caller abort signal', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode('event: snapshot\ndata: {"cursor":9,"events":[],"themes":{}}\n\n')
            )
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
      )
    )
    const controller = new AbortController()
    const messages: unknown[] = []

    await openCommunityOverlayStream({
      publicKey: KEY,
      afterId: 7,
      signal: controller.signal,
      onMessage: message => messages.push(message),
      fetchImpl: fetchMock,
    })

    expect(fetchMock).toHaveBeenCalledWith(`${API_ENDPOINTS.communityOverlay.stream}?after_id=7`, {
      headers: { 'X-Overlay-Key': KEY },
      signal: controller.signal,
    })
    expect(messages).toEqual([{ type: 'snapshot', cursor: 9, events: [], themes: {} }])
  })

  it('rejects HTML fail-open responses before JSON parsing', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response('<!doctype html>', { status: 200, headers: { 'Content-Type': 'text/html' } })
      )

    await expect(
      openCommunityOverlayStream({
        publicKey: KEY,
        signal: new AbortController().signal,
        onMessage: vi.fn(),
        fetchImpl: fetchMock,
      })
    ).rejects.toThrow('text/event-stream')
  })
})
