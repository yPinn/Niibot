import { renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'

import { useDocumentTitle } from '@/hooks/useDocumentTitle'

describe('useDocumentTitle', () => {
  beforeEach(() => {
    document.title = ''
  })

  it('appends " | Niibot" suffix to the given title', () => {
    renderHook(() => useDocumentTitle('Dashboard'))
    expect(document.title).toBe('Dashboard | Niibot')
  })

  it('does not double-append the suffix when the title already ends with it', () => {
    renderHook(() => useDocumentTitle('Dashboard | Niibot'))
    expect(document.title).toBe('Dashboard | Niibot')
  })

  it('resets the title to "Niibot" on unmount', () => {
    const { unmount } = renderHook(() => useDocumentTitle('Dashboard'))
    expect(document.title).toBe('Dashboard | Niibot')
    unmount()
    expect(document.title).toBe('Niibot')
  })
})
