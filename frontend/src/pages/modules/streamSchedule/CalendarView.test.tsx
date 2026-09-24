import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { StreamSchedule } from '@/api/streamSchedule'

import { todayLocalDate, weekdayOf } from './calendar'
import { CalendarView } from './CalendarView'

function schedule(overrides: Partial<StreamSchedule>): StreamSchedule {
  return {
    id: 1,
    channel_id: 'chan1',
    kind: 'recurring',
    weekday: 0,
    specific_date: null,
    start_time: '20:00:00',
    duration_minutes: 180,
    title_template: '週一固定台',
    enabled: true,
    created_at: null,
    updated_at: null,
    ...overrides,
  }
}

/** Day cells (month grid cells and week-timeline day rows both use the same
 * aria-label shape) are labelled with their full ISO date, not the bare
 * day-of-month number — month view repeats day-of-month numbers across the
 * leading/trailing padding days from adjacent months, so a query on the bare
 * number would be ambiguous. */
function dayButton(dateStr: string) {
  return screen.getByRole('button', { name: new RegExp(`^${dateStr}：`) })
}

function dayButtons() {
  return screen.getAllByRole('button', { name: /^\d{4}-\d{2}-\d{2}：/ })
}

describe('CalendarView', () => {
  it('shows a resolved schedule on the matching weekday and clicking it edits that schedule', async () => {
    const todayWeekday = weekdayOf(new Date())
    const recurring = schedule({ id: 1, weekday: todayWeekday })
    const onEditSchedule = vi.fn()
    const user = userEvent.setup()

    render(
      <CalendarView
        schedules={[recurring]}
        onEditSchedule={onEditSchedule}
        onCreateForDate={vi.fn()}
      />
    )

    await user.click(dayButton(todayLocalDate()))

    expect(onEditSchedule).toHaveBeenCalledWith(recurring, todayLocalDate())
  })

  it('clicking an empty day calls onCreateForDate with that date', async () => {
    const onCreateForDate = vi.fn()
    const user = userEvent.setup()
    render(
      <CalendarView schedules={[]} onEditSchedule={vi.fn()} onCreateForDate={onCreateForDate} />
    )

    await user.click(dayButton(todayLocalDate()))

    expect(onCreateForDate).toHaveBeenCalledWith(todayLocalDate())
  })

  it('defaults to week view (7 days) and can switch to month view (a multiple of 7, up to 6 weeks)', async () => {
    const user = userEvent.setup()
    render(<CalendarView schedules={[]} onEditSchedule={vi.fn()} onCreateForDate={vi.fn()} />)

    expect(dayButtons()).toHaveLength(7)

    await user.click(screen.getByRole('tab', { name: '月' }))

    const monthCount = dayButtons().length
    expect(monthCount % 7).toBe(0)
    expect(monthCount).toBeGreaterThanOrEqual(28)
    expect(monthCount).toBeLessThanOrEqual(42)
  })

  it('"今天" jumps back to the current week after navigating away', async () => {
    const user = userEvent.setup()
    render(<CalendarView schedules={[]} onEditSchedule={vi.fn()} onCreateForDate={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: '下一週' }))
    await user.click(screen.getByRole('button', { name: '下一週' }))
    await user.click(screen.getByRole('button', { name: '今天' }))

    expect(dayButton(todayLocalDate())).toBeInTheDocument()
  })

  it('"今天" jumps back to the month containing today after navigating away in month view', async () => {
    const user = userEvent.setup()
    render(<CalendarView schedules={[]} onEditSchedule={vi.fn()} onCreateForDate={vi.fn()} />)

    await user.click(screen.getByRole('tab', { name: '月' }))
    await user.click(screen.getByRole('button', { name: '下一個月' }))
    await user.click(screen.getByRole('button', { name: '下一個月' }))
    await user.click(screen.getByRole('button', { name: '今天' }))

    expect(dayButton(todayLocalDate())).toBeInTheDocument()
  })
})
