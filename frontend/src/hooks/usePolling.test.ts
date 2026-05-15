import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { usePolling } from '@/hooks/usePolling'

describe('usePolling', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('calls fetchFn immediately on mount', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling({ fetchFn, intervalMs: 1_000 }))
    expect(fetchFn).toHaveBeenCalledTimes(1)
  })

  it('calls fetchFn again after each interval tick', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling({ fetchFn, intervalMs: 1_000 }))
    vi.advanceTimersByTime(3_000)
    // 1 immediate + 3 interval ticks
    expect(fetchFn).toHaveBeenCalledTimes(4)
  })

  it('stops polling after unmount', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    const { unmount } = renderHook(() => usePolling({ fetchFn, intervalMs: 1_000 }))
    vi.advanceTimersByTime(2_000) // 1 immediate + 2 ticks = 3 calls
    unmount()
    vi.advanceTimersByTime(5_000) // no new calls after unmount
    expect(fetchFn).toHaveBeenCalledTimes(3)
  })

  it('does not call fetchFn when enabled is false', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling({ fetchFn, intervalMs: 1_000, enabled: false }))
    vi.advanceTimersByTime(5_000)
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it('skips the immediate call when skipInitialCall is true', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    renderHook(() => usePolling({ fetchFn, intervalMs: 1_000, skipInitialCall: true }))
    // no immediate call on mount
    expect(fetchFn).not.toHaveBeenCalled()
    vi.advanceTimersByTime(3_000)
    // only interval ticks, no leading call
    expect(fetchFn).toHaveBeenCalledTimes(3)
  })

  it('starts polling when enabled transitions from false to true', () => {
    const fetchFn = vi.fn().mockResolvedValue(undefined)
    const { rerender } = renderHook(
      ({ enabled }: { enabled: boolean }) => usePolling({ fetchFn, intervalMs: 1_000, enabled }),
      { initialProps: { enabled: false } }
    )
    vi.advanceTimersByTime(2_000)
    expect(fetchFn).not.toHaveBeenCalled()

    rerender({ enabled: true })
    // immediate call fires on enable
    expect(fetchFn).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(2_000)
    expect(fetchFn).toHaveBeenCalledTimes(3)
  })
})
