import { describe, expect, it, vi } from 'vitest'

import { openSseStream, SseFrameParser } from './sseStream'

describe('SseFrameParser', () => {
  it('splits frames across multiple push calls', () => {
    const frames: unknown[] = []
    const parser = new SseFrameParser(frame => frames.push(frame))

    parser.push('event: foo\ndata: par')
    parser.push('tial\n\n')

    expect(frames).toEqual([{ event: 'foo', data: 'partial' }])
  })

  it('joins multi-line data fields with newlines', () => {
    const frames: unknown[] = []
    const parser = new SseFrameParser(frame => frames.push(frame))

    parser.push('event: foo\ndata: line1\ndata: line2\n\n')

    expect(frames).toEqual([{ event: 'foo', data: 'line1\nline2' }])
  })

  it('drops a frame with no event name (e.g. a bare keep-alive comment)', () => {
    const frames: unknown[] = []
    const parser = new SseFrameParser(frame => frames.push(frame))

    parser.push(': keep-alive\n\nevent: real\ndata: x\n\n')

    expect(frames).toEqual([{ event: 'real', data: 'x' }])
  })
})

describe('openSseStream', () => {
  it('rejects a non-2xx response before touching the body', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(null, { status: 500, headers: { 'Content-Type': 'text/event-stream' } })
      )

    await expect(
      openSseStream({
        url: 'https://example.test/stream',
        signal: new AbortController().signal,
        onFrame: vi.fn(),
        fetchImpl: fetchMock,
      })
    ).rejects.toThrow('text/event-stream')
  })

  it('rejects a response with no body', async () => {
    const response = new Response(null, {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    })
    Object.defineProperty(response, 'body', { value: null })
    const fetchMock = vi.fn().mockResolvedValue(response)

    await expect(
      openSseStream({
        url: 'https://example.test/stream',
        signal: new AbortController().signal,
        onFrame: vi.fn(),
        fetchImpl: fetchMock,
      })
    ).rejects.toThrow('no body')
  })

  it('pumps every chunk to the frame parser until the stream closes', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('event: a\ndata: 1\n\n'))
            controller.enqueue(encoder.encode('event: b\ndata: 2\n\n'))
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream; charset=utf-8' } }
      )
    )
    const frames: unknown[] = []

    await openSseStream({
      url: 'https://example.test/stream',
      signal: new AbortController().signal,
      onFrame: frame => frames.push(frame),
      fetchImpl: fetchMock,
    })

    expect(frames).toEqual([
      { event: 'a', data: '1' },
      { event: 'b', data: '2' },
    ])
  })
})
