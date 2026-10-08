import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CloudflareUsage, RateLimitSnapshot } from '@/api/admin'

import { CloudflareQuotaCard, RateLimitDigest, RateLimitSection } from './RateLimitViews'

function snap(overrides: Partial<RateLimitSnapshot> = {}): RateLimitSnapshot {
  return {
    name: 'x',
    group: 'inbound',
    limit: 10,
    window_seconds: 60,
    used: 0,
    keys: 0,
    ...overrides,
  }
}

const CF: CloudflareUsage = {
  configured: true,
  limit: 100_000,
  day_start: '2026-10-09T00:00:00+00:00',
  reset_at: '2026-10-10T00:00:00+00:00',
  workers_requests: 1_000,
  pages_requests: 2_000,
  total_requests: 3_000,
  errors: [],
  fetched_at: null,
}

describe('RateLimitSection', () => {
  it('lists throttles most pressing first', () => {
    render(
      <RateLimitSection
        title="API Server"
        icon="fa-solid fa-server"
        items={[
          snap({ name: 'quiet', used: 1, keys: 1 }),
          snap({ name: 'busy', used: 10, keys: 1, rejected: 4 }),
        ]}
      />
    )
    const rows = screen.getAllByTestId('rate-limit-row')
    expect(rows[0]).toHaveTextContent('busy')
    expect(rows[0]).toHaveTextContent('10/10 · 1m')
    expect(rows[0]).toHaveTextContent('拒絕 4')
    expect(screen.getByText('limited')).toBeInTheDocument()
  })

  it('shows an offline service', () => {
    render(<RateLimitSection title="Discord Bot" icon="fa-brands fa-discord" items={null} />)
    expect(screen.getByText('服務離線，無法取得限流狀態')).toBeInTheDocument()
  })
})

describe('RateLimitDigest', () => {
  it('shows only active throttles, at most three, and links to the tab', () => {
    const onOpen = vi.fn()
    render(
      <RateLimitDigest
        items={[
          snap({ name: 'a', used: 1, keys: 1 }),
          snap({ name: 'b', used: 2, keys: 1 }),
          snap({ name: 'c', used: 3, keys: 1 }),
          snap({ name: 'd', used: 4, keys: 1 }),
          snap({ name: 'idle' }),
        ]}
        onOpen={onOpen}
      />
    )
    expect(screen.getAllByTestId('rate-limit-row')).toHaveLength(3)
    expect(screen.queryByText('idle', { selector: 'span.font-mono' })).toBeNull()
    fireEvent.click(screen.getByText(/查看限流/))
    expect(onOpen).toHaveBeenCalled()
  })

  it('says when everything is idle', () => {
    render(<RateLimitDigest items={[snap(), snap({ name: 'y' })]} onOpen={() => {}} />)
    expect(screen.getByText('2 項皆閒置')).toBeInTheDocument()
  })
})

describe('CloudflareQuotaCard', () => {
  it('shows today’s total against the quota and the breakdown', () => {
    render(<CloudflareQuotaCard usage={CF} />)
    expect(screen.getByText('3,000 / 100,000')).toBeInTheDocument()
    expect(screen.getByText('1,000 · 2,000')).toBeInTheDocument()
  })

  it('explains how to enable it when unconfigured', () => {
    render(<CloudflareQuotaCard usage={{ ...CF, configured: false }} />)
    expect(screen.getByText('未設定')).toBeInTheDocument()
    expect(screen.getByText(/CLOUDFLARE_API_TOKEN/)).toBeInTheDocument()
  })

  it('surfaces a dataset error without hiding the rest', () => {
    render(
      <CloudflareQuotaCard
        usage={{
          ...CF,
          pages_requests: null,
          errors: ['pagesFunctionsInvocationsAdaptiveGroups: x'],
        }}
      />
    )
    expect(screen.getByText('pagesFunctionsInvocationsAdaptiveGroups: x')).toBeInTheDocument()
    expect(screen.getByText('3,000 / 100,000')).toBeInTheDocument()
  })
})
