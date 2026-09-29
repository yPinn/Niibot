import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/streamSchedule', () => ({
  cancelStreamScheduleOccurrence: vi.fn(),
  createStreamSchedule: vi.fn(),
  deleteStreamSchedule: vi.fn(),
  searchStreamScheduleGames: vi.fn().mockResolvedValue([]),
  updateStreamSchedule: vi.fn(),
}))

vi.mock('./SegmentList', () => ({
  SegmentList: () => <div data-testid="segment-list" />,
}))

import {
  createStreamSchedule,
  searchStreamScheduleGames,
  type StreamSchedule,
  updateStreamSchedule,
} from '@/api/streamSchedule'

import { addDays, calendarDate, toDateStr, todayInTimeZone, weekdayInTimeZone } from './calendar'
import { WEEKDAY_LABELS } from './constants'
import { ScheduleSheet } from './ScheduleSheet'

const TIMEZONE = 'Asia/Taipei'
const SCHEDULE: StreamSchedule = {
  id: 1,
  channel_id: 'channel-1',
  kind: 'recurring',
  weekday: 0,
  specific_date: null,
  start_time: '20:00:00',
  duration_minutes: 180,
  title_template: '原本標題',
  enabled: true,
  created_at: null,
  updated_at: null,
}

const mockCreate = vi.mocked(createStreamSchedule)
const mockSearch = vi.mocked(searchStreamScheduleGames)
const mockUpdate = vi.mocked(updateStreamSchedule)

function renderSheet(editing: Parameters<typeof ScheduleSheet>[0]['editing']) {
  const onClose = vi.fn()
  const onSaved = vi.fn()
  render(
    <ScheduleSheet
      editing={editing}
      timezone={TIMEZONE}
      onSaved={onSaved}
      onDeleted={vi.fn()}
      onOccurrenceCancelled={vi.fn()}
      onClose={onClose}
    />
  )
  return { onClose, onSaved }
}

describe('ScheduleSheet create flow', () => {
  beforeEach(() => {
    mockCreate.mockReset()
    mockSearch.mockReset()
    mockSearch.mockResolvedValue([])
    mockUpdate.mockReset()
  })

  it('keeps one create entry with schedule type as the first in-sheet decision', () => {
    renderSheet({ mode: 'create' })

    expect(screen.getByRole('heading', { name: '新增每週固定排程' })).toBeInTheDocument()
    expect(screen.getByRole('tablist', { name: '排程類型' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '每週固定' })).toHaveAttribute('data-state', 'active')
    expect(screen.getByRole('tab', { name: '單次排程' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立排程' })).toBeInTheDocument()
  })

  it('defaults the weekday from the configured timezone', () => {
    renderSheet({ mode: 'create' })

    const expected = WEEKDAY_LABELS[weekdayInTimeZone(new Date(), TIMEZONE)]
    expect(screen.getByRole('combobox', { name: '星期' })).toHaveTextContent(expected)
  })

  it('limits one-off dates to today or later and explains an invalid past date inline', async () => {
    const user = userEvent.setup()
    renderSheet({ mode: 'create' })
    await user.click(screen.getByRole('tab', { name: '單次排程' }))

    const today = todayInTimeZone(TIMEZONE)
    const yesterday = toDateStr(addDays(calendarDate(today), -1))
    const dateInput = screen.getByLabelText('日期')
    expect(dateInput).toHaveAttribute('min', today)

    fireEvent.change(dateInput, { target: { value: yesterday } })

    expect(dateInput).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('日期不能早於今天')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立排程' })).toBeDisabled()
  })

  it('does not send the hidden opening title when saving schedule metadata', async () => {
    mockUpdate.mockResolvedValue(SCHEDULE)
    const user = userEvent.setup()
    renderSheet({ mode: 'edit', schedule: SCHEDULE })

    fireEvent.change(screen.getByLabelText('開始時間'), { target: { value: '21:00' } })
    await user.click(screen.getByRole('button', { name: '儲存變更' }))

    await waitFor(() =>
      expect(mockUpdate).toHaveBeenCalledWith(1, {
        start_time: '21:00:00',
        duration_minutes: 120,
        enabled: true,
      })
    )
  })

  it('requires a Twitch category result instead of accepting unselected search text', async () => {
    mockSearch.mockResolvedValue([{ id: '509658', name: 'Just Chatting', box_art_url: null }])
    const user = userEvent.setup()
    renderSheet({ mode: 'create' })

    await user.type(screen.getByRole('combobox', { name: '遊戲分類（選填）' }), 'Just')

    expect(screen.getByText('請從搜尋結果選擇分類')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '建立排程' })).toBeDisabled()

    await user.click(await screen.findByRole('option', { name: 'Just Chatting' }))
    expect(screen.getByRole('button', { name: '建立排程' })).toBeEnabled()
  })

  it('warns before discarding an unsaved new schedule', async () => {
    const user = userEvent.setup()
    const { onClose } = renderSheet({ mode: 'create' })

    await user.type(screen.getByLabelText('開台標題（選填）'), '還沒存的內容')
    await user.click(screen.getByRole('button', { name: '關閉' }))

    expect(screen.getByRole('alertdialog', { name: '放棄未儲存的排程？' })).toBeInTheDocument()
    expect(onClose).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: '放棄變更' }))
    expect(onClose).toHaveBeenCalledOnce()
  })

  it('confirms creation and exposes segment settings without creating another entry flow', async () => {
    mockCreate.mockResolvedValue(SCHEDULE)
    const user = userEvent.setup()
    renderSheet({ mode: 'create' })

    await user.click(screen.getByRole('button', { name: '建立排程' }))

    expect(await screen.findByText('排程已建立，可繼續新增分段。')).toBeInTheDocument()
    expect(screen.getByTestId('segment-list')).toBeInTheDocument()
  })
})
