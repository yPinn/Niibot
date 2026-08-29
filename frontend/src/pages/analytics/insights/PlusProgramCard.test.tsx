import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { PlusProgramEstimate } from '@/api/analytics'

import { PlusProgramCard } from './PlusProgramCard'

const ESTIMATE: PlusProgramEstimate = {
  confirmed_points: 120,
  confirmed_subs: 80,
  pending_points: 200,
  pending_subs: 150,
  tier_breakdown: { t1: 60, t2: 10, t3: 10 },
  plan_confirmed: '60/40',
  plan_ceiling: '70/30',
  data_as_of: null,
}

const base = { loading: false, refreshing: false, locked: false, onRefresh: vi.fn() }

describe('PlusProgramCard', () => {
  it('shows a lock overlay for non-affiliates', () => {
    render(<PlusProgramCard {...base} estimate={null} locked />)
    expect(screen.getByText('需要實況盟友資格')).toBeInTheDocument()
  })

  it('shows a skeleton while loading', () => {
    const { container } = render(<PlusProgramCard {...base} estimate={null} loading />)
    expect(container.querySelector('[role="progressbar"]')).toBeNull()
  })

  it('renders nothing when there is no estimate', () => {
    const { container } = render(<PlusProgramCard {...base} estimate={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the confirmed points, split and the sub shortfall to the next threshold', () => {
    render(<PlusProgramCard {...base} estimate={ESTIMATE} />)
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('等級 1（60/40）')).toBeInTheDocument()
    expect(screen.getByText(/已確認 80 位付費訂閱/)).toBeInTheDocument()
    expect(screen.getByText(/另 150 位待確認來源（最高再 \+200 點）/)).toBeInTheDocument()
    // 300 - 120 = 180 more points => Tier 1 x180 / Tier 2 x90 / Tier 3 x30
    expect(screen.getByText('距 等級 2（70/30） 還差 180 點')).toBeInTheDocument()
    expect(screen.getByText('層級 1 ×180')).toBeInTheDocument()
    expect(screen.getByText('層級 3 ×30')).toBeInTheDocument()
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '120')
    expect(bar).toHaveAttribute('aria-valuemax', '300')
  })

  it('calls onRefresh when the refresh button is clicked', async () => {
    const onRefresh = vi.fn()
    render(<PlusProgramCard {...base} estimate={ESTIMATE} onRefresh={onRefresh} />)
    await userEvent.click(screen.getByRole('button', { name: '重新整理訂閱資料' }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('reports the top split with no remaining target', () => {
    render(
      <PlusProgramCard
        {...base}
        estimate={{ ...ESTIMATE, confirmed_points: 320, plan_confirmed: '70/30' }}
      />
    )
    expect(screen.getByText('已達等級 2（70/30）')).toBeInTheDocument()
  })
})
