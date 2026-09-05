import { describe, expect, it, vi } from 'vitest'

import { API_ENDPOINTS } from './config'
import { openVideoQueueStream } from './videoQueueStream'

const USERNAME = 'teststreamer'

describe('openVideoQueueStream', () => {
  it('connects to the username-scoped stream URL with the caller abort signal', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'event: snapshot\ndata: {"current":null,"queue":[],"queue_size":0,"total_queued_duration":null}\n\n'
              )
            )
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
      )
    )
    const controller = new AbortController()
    const messages: unknown[] = []

    await openVideoQueueStream({
      username: USERNAME,
      signal: controller.signal,
      onMessage: message => messages.push(message),
      fetchImpl: fetchMock,
    })

    expect(fetchMock).toHaveBeenCalledWith(API_ENDPOINTS.videoQueue.stream(USERNAME), {
      headers: undefined,
      signal: controller.signal,
    })
    expect(messages).toEqual([
      { type: 'snapshot', current: null, queue: [], queue_size: 0, total_queued_duration: null },
    ])
  })

  it('drops a frame with malformed JSON', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('event: update\ndata: not-json\n\n'))
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
      )
    )
    const onMessage = vi.fn()

    await openVideoQueueStream({
      username: USERNAME,
      signal: new AbortController().signal,
      onMessage,
      fetchImpl: fetchMock,
    })

    expect(onMessage).not.toHaveBeenCalled()
  })

  it('drops a frame that does not match the expected shape', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('event: update\ndata: {"unexpected":true}\n\n'))
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
      )
    )
    const onMessage = vi.fn()

    await openVideoQueueStream({
      username: USERNAME,
      signal: new AbortController().signal,
      onMessage,
      fetchImpl: fetchMock,
    })

    expect(onMessage).not.toHaveBeenCalled()
  })

  it('ignores heartbeat frames', async () => {
    const encoder = new TextEncoder()
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        new ReadableStream({
          start(controller) {
            controller.enqueue(encoder.encode('event: heartbeat\ndata: {"at":"2026-01-01"}\n\n'))
            controller.close()
          },
        }),
        { status: 200, headers: { 'Content-Type': 'text/event-stream' } }
      )
    )
    const onMessage = vi.fn()

    await openVideoQueueStream({
      username: USERNAME,
      signal: new AbortController().signal,
      onMessage,
      fetchImpl: fetchMock,
    })

    expect(onMessage).not.toHaveBeenCalled()
  })

  it('rejects HTML fail-open responses before JSON parsing', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response('<!doctype html>', { status: 200, headers: { 'Content-Type': 'text/html' } })
      )

    await expect(
      openVideoQueueStream({
        username: USERNAME,
        signal: new AbortController().signal,
        onMessage: vi.fn(),
        fetchImpl: fetchMock,
      })
    ).rejects.toThrow('text/event-stream')
  })
})
