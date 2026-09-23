import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SourceSettingsPanel } from './SourceSettingsCard'

describe('SourceSettingsPanel', () => {
  it('places channel points before Donate and explains the shared duration cap', () => {
    render(
      <SourceSettingsPanel
        draft={{ maxRedemptionDuration: '600' }}
        onField={vi.fn()}
        redemptionEnabled
        onToggleRedemption={vi.fn()}
      />
    )

    const points = screen.getByRole('heading', { name: '頻道點數' })
    const donate = screen.getByRole('heading', { name: 'Donate' })
    expect(points.compareDocumentPosition(donate) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByText(/較短的上限為準/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '前往 Donate 設定' })).toHaveAttribute(
      'href',
      '/settings'
    )
  })
})
