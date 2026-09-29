import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/streamSchedule', () => ({
  searchStreamScheduleGames: vi.fn(),
}))

import {
  searchStreamScheduleGames,
  type StreamSchedule,
  type StreamScheduleSegment,
} from '@/api/streamSchedule'

import {
  NextScheduleCard,
  NextScheduleCardEmpty,
  NextScheduleCardSkeleton,
} from './NextScheduleCard'

const mockSearch = vi.mocked(searchStreamScheduleGames)

const schedule: StreamSchedule = {
  id: 7,
  channel_id: 'channel-1',
  kind: 'recurring',
  weekday: 2,
  specific_date: null,
  start_time: '20:00:00',
  duration_minutes: 180,
  title_template: '備用標題',
  enabled: true,
  created_at: null,
  updated_at: null,
}

const opening: StreamScheduleSegment = {
  id: 9,
  channel_id: 'channel-1',
  schedule_id: 7,
  offset_minutes: 0,
  title_template: '深夜聊聊',
  game_id: '509658',
  game_name: 'Just Chatting',
  sort_order: 0,
}

describe('NextScheduleCard', () => {
  beforeEach(() => mockSearch.mockReset())

  it('presents the next stream as a structured row with its cover, title, date and time', async () => {
    mockSearch.mockResolvedValue([
      {
        id: '509658',
        name: 'Just Chatting',
        box_art_url: 'https://static.example/{width}x{height}.jpg',
      },
    ])

    render(
      <NextScheduleCard
        date="2026-09-30"
        schedule={schedule}
        opening={opening}
        timezone="Asia/Taipei"
      />
    )

    expect(screen.getByRole('region', { name: '下一場直播' })).toHaveClass('min-h-48', 'sm:min-h-0')
    expect(screen.getByRole('heading', { name: '深夜聊聊' })).toBeInTheDocument()
    expect(screen.getByText('Just Chatting')).toBeInTheDocument()
    expect(screen.getByText(/2026 年 9 月 30 日/)).toBeInTheDocument()
    expect(screen.getByText(/週三/)).toBeInTheDocument()
    expect(screen.getByText('20:00–23:00')).toBeInTheDocument()
    expect(screen.getByText('GMT+8')).toBeInTheDocument()
    expect(screen.getByText('每週固定')).toBeInTheDocument()

    const cover = await screen.findByRole('img', { name: 'Just Chatting 分類封面' })
    expect(cover).toHaveAttribute('src', 'https://static.example/96x128.jpg')
    expect(cover).toHaveAttribute('width', '96')
    expect(cover).toHaveAttribute('height', '128')
    expect(cover).toHaveAttribute('draggable', 'false')
    expect(cover).toHaveClass('select-none')
  })

  it('reserves the final row and cover dimensions while loading', () => {
    render(<NextScheduleCardSkeleton />)

    expect(screen.getByRole('region', { name: '載入下一場直播' }))
      .toHaveAttribute('aria-busy', 'true')
      .toHaveClass('min-h-48', 'sm:min-h-0')
    expect(screen.getByTestId('next-schedule-cover-skeleton')).toHaveClass(
      'h-24',
      'w-18',
      'sm:h-28',
      'sm:w-21',
      'select-none'
    )
  })

  it('uses the same cover slot in the empty state so the calendar never jumps', () => {
    render(<NextScheduleCardEmpty />)

    expect(screen.getByRole('region', { name: '下一場直播' })).toHaveClass('min-h-48', 'sm:min-h-0')
    expect(screen.getByText('尚無即將到來的排程')).toBeInTheDocument()
    expect(screen.getByTestId('next-schedule-empty-cover')).toHaveClass(
      'h-24',
      'w-18',
      'sm:h-28',
      'sm:w-21',
      'select-none'
    )
  })

  it('keeps a stable visual placeholder when no category is configured', () => {
    render(
      <NextScheduleCard
        date="2026-09-30"
        schedule={{ ...schedule, kind: 'one_off', weekday: null, specific_date: '2026-09-30' }}
        opening={{ ...opening, title_template: '', game_id: null, game_name: null }}
        timezone="Asia/Taipei"
      />
    )

    expect(screen.getByRole('heading', { name: '備用標題' })).toBeInTheDocument()
    expect(screen.getByText('未設定分類')).toBeInTheDocument()
    expect(screen.getByRole('img', { name: '未設定分類封面' })).toBeInTheDocument()
    expect(screen.getByText('單次排程')).toBeInTheDocument()
    expect(mockSearch).not.toHaveBeenCalled()
  })

  it('keeps the category readable when Twitch box art cannot be loaded', async () => {
    mockSearch.mockResolvedValue([])

    render(
      <NextScheduleCard
        date="2026-09-30"
        schedule={schedule}
        opening={{ ...opening, game_id: 'unavailable-game', game_name: 'Unavailable Game' }}
        timezone="Asia/Taipei"
      />
    )

    expect(screen.getByText('Unavailable Game')).toBeInTheDocument()
    expect(
      await screen.findByRole('img', { name: 'Unavailable Game 分類封面無法載入' })
    ).toBeInTheDocument()
  })
})
