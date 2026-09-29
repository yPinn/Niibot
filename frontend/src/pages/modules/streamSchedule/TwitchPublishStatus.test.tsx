import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { StreamSchedulePublishStatus } from '@/api/streamSchedule'

import { TwitchPublishStatus } from './TwitchPublishStatus'

function status(overrides: Partial<StreamSchedulePublishStatus> = {}): StreamSchedulePublishStatus {
  return {
    status: 'error',
    pending_count: 0,
    synced_count: 0,
    blocked_count: 0,
    error_count: 1,
    last_error_code: 'provider_unavailable',
    last_synced_at: null,
    ...overrides,
  }
}

describe('TwitchPublishStatus', () => {
  it('shows a compact synced confirmation without adding another settings entry', () => {
    render(
      <TwitchPublishStatus
        value={status({ status: 'synced', synced_count: 2, error_count: 0 })}
        capabilityAvailable
        retrying={false}
        onRetry={vi.fn()}
      />
    )

    expect(screen.getByText('已同步至 Twitch 行程表')).toBeInTheDocument()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })

  it('leaves missing-scope recovery to the existing capability alert', () => {
    const { container } = render(
      <TwitchPublishStatus
        value={status({ status: 'blocked', blocked_count: 1, last_error_code: 'missing_scope' })}
        capabilityAvailable={false}
        retrying={false}
        onRetry={vi.fn()}
      />
    )

    expect(container).toBeEmptyDOMElement()
  })

  it('offers one retry action for a temporary Twitch failure', () => {
    const onRetry = vi.fn()
    render(
      <TwitchPublishStatus
        value={status()}
        capabilityAvailable
        retrying={false}
        onRetry={onRetry}
      />
    )

    expect(screen.getByText('Twitch 暫時無法同步，請稍後重試。')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '重新同步' }))
    expect(onRetry).toHaveBeenCalledOnce()
  })
})
