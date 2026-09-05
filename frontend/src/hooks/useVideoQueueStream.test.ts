import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { VideoQueueStreamMessage } from '@/api/videoQueueStream'
import { useVideoQueueStream } from '@/hooks/useVideoQueueStream'

const openVideoQueueStream = vi.hoisted(() => vi.fn())

vi.mock('@/api/videoQueueStream', () => ({ openVideoQueueStream }))

interface StreamCall {
  username: string
  signal: AbortSignal
  onMessage: (m: VideoQueueStreamMessage) => void
}

const SNAPSHOT: VideoQueueStreamMessage = {
  type: 'snapshot',
  current: null,
  queue: [],
  queue_size: 0,
  total_queued_duration: null,
}

describe('useVideoQueueStream', () => {
  beforeEach(() => {
    // A stream that never settles — mirrors a live long-lived connection.
    openVideoQueueStream.mockImplementation(() => new Promise<void>(() => {}))
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('opens the stream for the given username and applies frames', async () => {
    const { result } = renderHook(() => useVideoQueueStream('streamer'))

    expect(openVideoQueueStream).toHaveBeenCalledTimes(1)
    const call = openVideoQueueStream.mock.calls[0][0] as StreamCall
    expect(call.username).toBe('streamer')
    expect(result.current.state).toBeNull()

    act(() => call.onMessage({ ...SNAPSHOT, queue_size: 3 }))
    await waitFor(() => expect(result.current.state?.queue_size).toBe(3))
  })

  it('does not open a stream without a username', () => {
    renderHook(() => useVideoQueueStream(undefined))
    expect(openVideoQueueStream).not.toHaveBeenCalled()
  })

  it('aborts the connection on unmount', () => {
    const { unmount } = renderHook(() => useVideoQueueStream('streamer'))
    const call = openVideoQueueStream.mock.calls[0][0] as StreamCall
    expect(call.signal.aborted).toBe(false)
    unmount()
    expect(call.signal.aborted).toBe(true)
  })

  it('exposes setState for optimistic updates', async () => {
    const { result } = renderHook(() => useVideoQueueStream('streamer'))
    act(() => result.current.setState({ ...SNAPSHOT, queue_size: 9 }))
    await waitFor(() => expect(result.current.state?.queue_size).toBe(9))
  })

  it('reconnects for a new username', () => {
    const { rerender } = renderHook(({ u }: { u: string }) => useVideoQueueStream(u), {
      initialProps: { u: 'first' },
    })
    expect(openVideoQueueStream.mock.calls[0][0].username).toBe('first')
    rerender({ u: 'second' })
    expect(openVideoQueueStream.mock.calls[1][0].username).toBe('second')
  })
})
