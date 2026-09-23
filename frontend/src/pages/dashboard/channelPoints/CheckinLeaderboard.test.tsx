import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { CheckinLeaderboard } from './CheckinLeaderboard'

describe('CheckinLeaderboard', () => {
  it('uses display name first and hides redundant handles and user ids', () => {
    render(
      <CheckinLeaderboard
        entries={[
          {
            rank: 1,
            user_id: '101',
            username: 'alice',
            display_name: 'Alice',
            total_days: 15,
            last_checkin_date: '2026-09-10',
          },
          {
            rank: 2,
            user_id: '202',
            username: 'bob_login',
            display_name: '小波',
            total_days: 8,
            last_checkin_date: '2026-09-09',
          },
          {
            rank: 3,
            user_id: '303',
            username: 'carol',
            display_name: null,
            total_days: 3,
            last_checkin_date: '2026-09-08',
          },
          {
            rank: 4,
            user_id: '404',
            username: 'dave',
            display_name: 'Dave',
            total_days: 1,
            last_checkin_date: '2026-09-07',
          },
        ]}
        loading={false}
        loadFailed={false}
        onRetry={vi.fn()}
      />
    )

    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.queryByText(/@alice/)).not.toBeInTheDocument()
    expect(screen.getByText(/@bob_login/)).toBeInTheDocument()
    expect(screen.getByText('carol')).toBeInTheDocument()
    expect(screen.queryByText('101')).not.toBeInTheDocument()
    expect(screen.queryByText('202')).not.toBeInTheDocument()
  })

  it('shows loading, retry, and empty states', async () => {
    const onRetry = vi.fn()
    const { rerender } = render(
      <CheckinLeaderboard entries={[]} loading loadFailed={false} onRetry={onRetry} />
    )

    expect(screen.getByLabelText('簽到排行榜載入中')).toBeInTheDocument()

    rerender(<CheckinLeaderboard entries={[]} loading={false} loadFailed onRetry={onRetry} />)
    await userEvent.click(screen.getByRole('button', { name: '重新載入排行榜' }))
    expect(onRetry).toHaveBeenCalledOnce()

    rerender(
      <CheckinLeaderboard entries={[]} loading={false} loadFailed={false} onRetry={onRetry} />
    )
    expect(screen.getByText('尚無簽到紀錄')).toBeInTheDocument()
  })
})
