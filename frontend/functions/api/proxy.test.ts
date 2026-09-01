import { describe, expect, it, vi } from 'vitest'

import { onRequest } from './[[path]]'

function context(path: string, signal: AbortSignal) {
  return {
    env: { API_BACKEND: 'https://api.example.test' },
    request: new Request(`https://niibot.example${path}`, { signal }),
  } as Parameters<typeof onRequest>[0]
}

describe('Pages API proxy', () => {
  it('keeps the exact GET stream connected to the caller with a bounded lease', async () => {
    const controller = new AbortController()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('stream'))
    const requestContext = context('/api/live-display/public/stream?after_id=4', controller.signal)

    await onRequest(requestContext)

    const upstreamSignal = fetchMock.mock.calls[0][1]?.signal
    expect(upstreamSignal).not.toBe(requestContext.request.signal)
    expect(upstreamSignal?.aborted).toBe(false)
    controller.abort()
    expect(upstreamSignal?.aborted).toBe(true)
    fetchMock.mockRestore()
  })

  it('aborts the upstream stream when its lease expires', async () => {
    const lease = new AbortController()
    const timeoutMock = vi.spyOn(AbortSignal, 'timeout').mockReturnValue(lease.signal)
    try {
      const controller = new AbortController()
      const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('stream'))

      await onRequest(context('/api/live-display/public/stream', controller.signal))
      const upstreamSignal = fetchMock.mock.calls[0][1]?.signal

      expect(timeoutMock).toHaveBeenCalledWith(5 * 60 * 1000)
      lease.abort()
      expect(upstreamSignal?.aborted).toBe(true)
      fetchMock.mockRestore()
    } finally {
      timeoutMock.mockRestore()
    }
  })

  it('retains the bounded timeout for all other API requests', async () => {
    const controller = new AbortController()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(Response.json({ ok: true }))

    await onRequest(context('/api/auth/twitch/oauth', controller.signal))

    expect(fetchMock.mock.calls[0][1]?.signal).not.toBe(controller.signal)
    fetchMock.mockRestore()
  })
})
