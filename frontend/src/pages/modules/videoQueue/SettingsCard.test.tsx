import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { SettingsCard } from './SettingsCard'

const draft = {
  maxDurationMinutes: '10',
  minViewCount: '0',
  replayCooldownHours: '0',
  maxPerUser: '0',
  userCooldownSeconds: '0',
  maxQueueSize: '20',
  maxRedemptionDuration: '600',
  volumePercent: '100',
}

describe('SettingsCard information architecture', () => {
  it('keeps source settings in the default tab with channel points before Donate', () => {
    render(
      <SettingsCard
        draft={draft}
        onField={vi.fn()}
        redemptionEnabled
        onToggleRedemption={vi.fn()}
        onSave={vi.fn()}
        saving={false}
      />
    )

    expect(screen.getByRole('tab', { name: '加入來源' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: '通用規則' })).toBeInTheDocument()

    const points = screen.getByRole('heading', { name: '頻道點數' })
    const donate = screen.getByRole('heading', { name: 'Donate' })
    expect(points.compareDocumentPosition(donate) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.queryByText('影片最長')).not.toBeInTheDocument()
  })

  it('switches to shared rules without rendering a second settings card', async () => {
    const user = userEvent.setup()
    const { container } = render(
      <SettingsCard
        draft={draft}
        onField={vi.fn()}
        redemptionEnabled
        onToggleRedemption={vi.fn()}
        onSave={vi.fn()}
        saving={false}
      />
    )

    await user.click(screen.getByRole('tab', { name: '通用規則' }))

    expect(screen.getByText('影片最長')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: '頻道點數' })).not.toBeInTheDocument()
    expect(container.querySelectorAll('[data-slot="card"]')).toHaveLength(1)
  })

  it('uses one shared save action for both settings tabs', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    render(
      <SettingsCard
        draft={draft}
        onField={vi.fn()}
        redemptionEnabled
        onToggleRedemption={vi.fn()}
        onSave={onSave}
        saving={false}
      />
    )

    const save = screen.getByRole('button', { name: '儲存設定' })
    expect(screen.getAllByRole('button', { name: /儲存/ })).toHaveLength(1)
    await user.click(save)
    expect(onSave).toHaveBeenCalledOnce()
  })
})
