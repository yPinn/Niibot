import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { reportSilent } from '@/lib/clientErrorReporter'

import { type StreamHelpers, useReconnectingStream } from './useReconnectingStream'

vi.mock('@/lib/clientErrorReporter', () => ({ reportSilent: vi.fn() }))

describe('useReconnectingStream', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0.5)
  })

  afterEach(() => {
    vi.mocked(reportSilent).mockClear()
    vi.mocked(Math.random).mockRestore()
    vi.useRealTimers()
  })

  it('starts connecting and flips to live once the caller reports a frame', () => {
    let helpers: StreamHelpers | undefined
    const connect = vi.fn((_signal: AbortSignal, h: StreamHelpers) => {
      helpers = h
      return new Promise<void>(() => {}) // never settles — a live connection
    })

    const { result } = renderHook(() =>
      useReconnectingStream({ enabled: true, label: 'test-stream', connect })
    )

    expect(result.current.status).toBe('connecting')
    expect(connect).toHaveBeenCalledTimes(1)

    act(() => helpers?.notifyLive())
    expect(result.current.status).toBe('live')
  })

  it('does not flip to reconnecting before the grace window elapses', async () => {
    const connect = vi.fn(async (_signal: AbortSignal, h: StreamHelpers) => {
      h.notifyLive()
    })

    const { result } = renderHook(() =>
      useReconnectingStream({ enabled: true, label: 'test-stream', connect })
    )
    // Flush the microtask queue so connect()'s resolution (and its .finally
    // scheduling the next attempt) has actually run.
    await act(async () => vi.advanceTimersByTimeAsync(0))
    expect(result.current.status).toBe('live')

    // A reconnect is scheduled (routine lease-renewal style end), but the
    // 3s grace window hasn't elapsed yet.
    await act(async () => vi.advanceTimersByTimeAsync(2_000))
    expect(result.current.status).toBe('live')
  })

  it('flips to reconnecting once a disconnect outlasts the grace window', async () => {
    // First attempt: reports live, then ends immediately (routine reconnect).
    // Every attempt after that never settles and never calls notifyLive —
    // simulating a stalled connection that outlasts the 3s grace window.
    const connect = vi
      .fn<(signal: AbortSignal, h: StreamHelpers) => Promise<void>>()
      .mockImplementationOnce(async (_signal, h) => {
        h.notifyLive()
      })
      .mockImplementation(() => new Promise<void>(() => {}))

    const { result } = renderHook(() =>
      useReconnectingStream({ enabled: true, label: 'test-stream', connect })
    )
    await act(async () => vi.advanceTimersByTimeAsync(0))
    expect(result.current.status).toBe('live')

    // ~1s reconnect delay for the second attempt to start, then the 3s
    // grace window on that attempt before it's declared reconnecting.
    await act(async () => vi.advanceTimersByTimeAsync(5_000))
    expect(result.current.status).toBe('reconnecting')
  })

  it('reports a rejected connect() attempt', async () => {
    const err = new Error('network down')
    const connect = vi.fn(() => Promise.reject(err))

    renderHook(() => useReconnectingStream({ enabled: true, label: 'test-stream', connect }))
    await act(async () => vi.advanceTimersByTimeAsync(0))

    expect(reportSilent).toHaveBeenCalledWith(err)
  })

  it('notifyStreamError reports immediately, independent of the grace window', () => {
    let helpers: StreamHelpers | undefined
    const connect = vi.fn((_signal: AbortSignal, h: StreamHelpers) => {
      helpers = h
      return new Promise<void>(() => {})
    })

    renderHook(() => useReconnectingStream({ enabled: true, label: 'test-stream', connect }))
    expect(connect).toHaveBeenCalledTimes(1)

    act(() => helpers?.notifyStreamError('STREAM.ITERATION_FAILED'))
    expect(reportSilent).toHaveBeenCalledTimes(1)
    expect(vi.mocked(reportSilent).mock.calls[0][0]).toBeInstanceOf(Error)
  })

  it('never calls connect while disabled', () => {
    const connect = vi.fn(() => new Promise<void>(() => {}))
    const { result } = renderHook(() =>
      useReconnectingStream({ enabled: false, label: 'test-stream', connect })
    )
    expect(connect).not.toHaveBeenCalled()
    expect(result.current.status).toBe('connecting')
  })
})
