import { act, renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useSortState } from '@/hooks/useSortState'

describe('useSortState', () => {
  it('initialises with the provided key and asc direction', () => {
    const { result } = renderHook(() => useSortState('name'))
    expect(result.current.sortKey).toBe('name')
    expect(result.current.sortDir).toBe('asc')
  })

  it('flips direction when the same key is toggled again', () => {
    const { result } = renderHook(() => useSortState('name'))
    act(() => result.current.toggleSort('name'))
    expect(result.current.sortDir).toBe('desc')
    act(() => result.current.toggleSort('name'))
    expect(result.current.sortDir).toBe('asc')
  })

  it('resets to asc when a different key is toggled', () => {
    const { result } = renderHook(() => useSortState<'name' | 'count'>('name'))
    act(() => result.current.toggleSort('name')) // name → desc
    act(() => result.current.toggleSort('count')) // new key → asc
    expect(result.current.sortKey).toBe('count')
    expect(result.current.sortDir).toBe('asc')
  })

  it('switching back to original key starts from asc', () => {
    const { result } = renderHook(() => useSortState<'name' | 'count'>('name'))
    act(() => result.current.toggleSort('count')) // count → asc
    act(() => result.current.toggleSort('name')) // back to name → asc
    expect(result.current.sortKey).toBe('name')
    expect(result.current.sortDir).toBe('asc')
  })
})
