import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useDebouncedValue } from '@/hooks/useDebouncedValue'

describe('useDebouncedValue', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns the initial value immediately', () => {
    const { result } = renderHook(() => useDebouncedValue('a', 300))
    expect(result.current).toBe('a')
  })

  it('delays updates until the value settles', () => {
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useDebouncedValue(value, 300),
      { initialProps: { value: 'a' } }
    )

    rerender({ value: 'ab' })
    expect(result.current).toBe('a')

    act(() => void vi.advanceTimersByTime(299))
    expect(result.current).toBe('a')

    act(() => void vi.advanceTimersByTime(1))
    expect(result.current).toBe('ab')
  })

  it('only emits the last value in a rapid burst', () => {
    const { result, rerender } = renderHook(
      ({ value }: { value: string }) => useDebouncedValue(value, 300),
      { initialProps: { value: '' } }
    )

    rerender({ value: 'h' })
    act(() => void vi.advanceTimersByTime(100))
    rerender({ value: 'he' })
    act(() => void vi.advanceTimersByTime(100))
    rerender({ value: 'hey' })
    act(() => void vi.advanceTimersByTime(299))
    expect(result.current).toBe('')

    act(() => void vi.advanceTimersByTime(1))
    expect(result.current).toBe('hey')
  })
})
