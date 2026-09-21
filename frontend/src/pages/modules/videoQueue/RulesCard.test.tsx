import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { type RulesDraft, RulesPanel } from './RulesCard'

const draft: RulesDraft = {
  maxDurationMinutes: '10',
  minViewCount: '0',
  replayCooldownHours: '0',
  maxPerUser: '0',
  userCooldownSeconds: '0',
  maxQueueSize: '20',
  maxRedemptionDuration: '600',
  volumePercent: '100',
}

describe('RulesPanel information architecture', () => {
  it('separates all-source, audience-source, and identifiable-viewer rules', () => {
    render(<RulesPanel draft={draft} onField={vi.fn()} />)

    expect(screen.getByText('所有來源')).toBeInTheDocument()
    expect(screen.getByText('觀眾加入來源')).toBeInTheDocument()
    expect(screen.getByText('可識別觀眾')).toBeInTheDocument()
    expect(screen.queryByText('用頻道點數兌換')).not.toBeInTheDocument()
  })
})
