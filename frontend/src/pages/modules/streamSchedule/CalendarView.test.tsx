import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { StreamSchedule } from '@/api/streamSchedule'

import { todayInTimeZone, weekdayInTimeZone } from './calendar'
import { CalendarView } from './CalendarView'

const TIMEZONE = 'Asia/Taipei'

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
  it('shows only the timezone offset in the week header', () => {
    render(
      <CalendarView
        schedules={[]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={vi.fn()}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={vi.fn()}
      />
    )

    expect(screen.getByText('GMT+8')).toBeInTheDocument()
    expect(screen.queryByText('Asia/Taipei')).not.toBeInTheDocument()
  })

  it('shows a resolved schedule on the matching weekday and clicking it edits that schedule', async () => {
    const todayWeekday = weekdayInTimeZone(new Date(), TIMEZONE)
    const recurring = schedule({ id: 1, weekday: todayWeekday })
    const onEditSchedule = vi.fn()
    const user = userEvent.setup()

    render(
      <CalendarView
        schedules={[recurring]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={onEditSchedule}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={vi.fn()}
      />
    )

    await user.click(dayButton(todayInTimeZone(TIMEZONE)))

    expect(onEditSchedule).toHaveBeenCalledWith(recurring, todayInTimeZone(TIMEZONE))
  })

  it('clicking an empty day calls onCreateForDate with that date', async () => {
    const onCreateForDate = vi.fn()
    const user = userEvent.setup()
    render(
      <CalendarView
        schedules={[]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={vi.fn()}
        onCreateForDate={onCreateForDate}
        onRestoreOccurrence={vi.fn()}
      />
    )

    await user.click(dayButton(todayInTimeZone(TIMEZONE)))

    expect(onCreateForDate).toHaveBeenCalledWith(todayInTimeZone(TIMEZONE))
  })

  it('shows multiple non-overlapping schedules on the same day', () => {
    const weekday = weekdayInTimeZone(new Date(), TIMEZONE)
    const first = schedule({ id: 1, weekday, start_time: '18:00:00', title_template: '第一場' })
    const second = schedule({ id: 2, weekday, start_time: '22:00:00', title_template: '第二場' })
    render(
      <CalendarView
        schedules={[first, second]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={vi.fn()}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: /第一場/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /第二場/ })).toBeInTheDocument()
  })

  it('shows a cancelled occurrence and restores it when clicked', async () => {
    const today = todayInTimeZone(TIMEZONE)
    const recurring = schedule({ id: 1, weekday: weekdayInTimeZone(new Date(), TIMEZONE) })
    const onRestoreOccurrence = vi.fn()
    const user = userEvent.setup()
    render(
      <CalendarView
        schedules={[recurring]}
        exceptions={[
          {
            id: 1,
            channel_id: 'chan1',
            recurring_schedule_id: 1,
            occurrence_date: today,
            kind: 'cancelled',
            replacement_schedule_id: null,
            created_at: null,
            updated_at: null,
          },
        ]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={vi.fn()}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={onRestoreOccurrence}
      />
    )

    await user.click(screen.getByRole('button', { name: `${today}：已取消，點擊恢復` }))
    expect(onRestoreOccurrence).toHaveBeenCalledWith(recurring, today)
  })

  it('renders the controlled week and month modes', () => {
    const props = {
      schedules: [],
      exceptions: [],
      timezone: TIMEZONE,
      onEditSchedule: vi.fn(),
      onCreateForDate: vi.fn(),
      onRestoreOccurrence: vi.fn(),
    }
    const { rerender } = render(<CalendarView {...props} mode="week" />)

    expect(dayButtons()).toHaveLength(7)

    rerender(<CalendarView {...props} mode="month" />)

    const monthCount = dayButtons().length
    expect(monthCount % 7).toBe(0)
    expect(monthCount).toBeGreaterThanOrEqual(28)
    expect(monthCount).toBeLessThanOrEqual(42)
  })

  it('"今天" jumps back to the current week after navigating away', async () => {
    const user = userEvent.setup()
    render(
      <CalendarView
        schedules={[]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="week"
        onEditSchedule={vi.fn()}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: '下一週' }))
    await user.click(screen.getByRole('button', { name: '下一週' }))
    await user.click(screen.getByRole('button', { name: '今天' }))

    expect(dayButton(todayInTimeZone(TIMEZONE))).toBeInTheDocument()
  })

  it('"今天" jumps back to the month containing today after navigating away in month view', async () => {
    const user = userEvent.setup()
    render(
      <CalendarView
        schedules={[]}
        exceptions={[]}
        timezone={TIMEZONE}
        mode="month"
        onEditSchedule={vi.fn()}
        onCreateForDate={vi.fn()}
        onRestoreOccurrence={vi.fn()}
      />
    )

    await user.click(screen.getByRole('button', { name: '下一個月' }))
    await user.click(screen.getByRole('button', { name: '下一個月' }))
    await user.click(screen.getByRole('button', { name: '今天' }))

    expect(dayButton(todayInTimeZone(TIMEZONE))).toBeInTheDocument()
  })
})
