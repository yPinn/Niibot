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

describe('PlusProgramCard', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(
      <PlusProgramCard estimate={null} loading refreshing={false} onRefresh={vi.fn()} />
    )
    expect(container.querySelector('[role="progressbar"]')).toBeNull()
  })

  it('renders nothing when there is no estimate', () => {
    const { container } = render(
      <PlusProgramCard estimate={null} loading={false} refreshing={false} onRefresh={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the confirmed points, split and the distance to the next threshold', () => {
    render(
      <PlusProgramCard estimate={ESTIMATE} loading={false} refreshing={false} onRefresh={vi.fn()} />
    )
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText(/60\/40/)).toBeInTheDocument()
    expect(screen.getByText(/確認付費 80 位 · 待確認 150 位（最多 \+200 點）/)).toBeInTheDocument()
    expect(screen.getByText(/距 70\/30 還差 180 點/)).toBeInTheDocument()
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '120')
    expect(bar).toHaveAttribute('aria-valuemax', '300')
  })

  it('calls onRefresh when the refresh button is clicked', async () => {
    const onRefresh = vi.fn()
    render(
      <PlusProgramCard
        estimate={ESTIMATE}
        loading={false}
        refreshing={false}
        onRefresh={onRefresh}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: /重新整理訂閱資料/ }))
    expect(onRefresh).toHaveBeenCalledOnce()
  })

  it('reports the top split with no remaining target', () => {
    render(
      <PlusProgramCard
        estimate={{ ...ESTIMATE, confirmed_points: 320, plan_confirmed: '70/30' }}
        loading={false}
        refreshing={false}
        onRefresh={vi.fn()}
      />
    )
    expect(screen.getByText('已達最高分潤級距')).toBeInTheDocument()
  })
})
