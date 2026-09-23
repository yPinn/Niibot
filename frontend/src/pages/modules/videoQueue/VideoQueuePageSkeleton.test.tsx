import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { VideoQueuePageSkeleton } from './VideoQueuePageSkeleton'

describe('VideoQueuePageSkeleton', () => {
  it('mirrors the two responsive 8/4 workspace rows', () => {
    const { container } = render(<VideoQueuePageSkeleton />)
    const rows = container.querySelectorAll('[data-layout="video-queue-row"]')

    expect(rows).toHaveLength(2)
    for (const row of rows) {
      expect(row).toHaveClass('lg:grid-cols-12')
      expect(row.querySelector('.lg\\:col-span-8')).toBeInTheDocument()
      expect(row.querySelector('.lg\\:col-span-4')).toBeInTheDocument()
    }
  })
})
