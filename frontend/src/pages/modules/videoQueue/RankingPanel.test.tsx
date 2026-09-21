import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { VideoQueueRankingEntry } from '@/api/videoQueue'

import { RankingPanel } from './RankingPanel'

const getVideoQueueRankings = vi.fn()

vi.mock('@/api/videoQueue', () => ({
  getVideoQueueRankings: (...args: unknown[]) => getVideoQueueRankings(...args),
}))

function ranking(overrides: Partial<VideoQueueRankingEntry> = {}): VideoQueueRankingEntry {
  return {
    rank: 1,
    video_type: 'youtube',
    video_id: 'dQw4w9WgXcQ',
    start_seconds: 0,
    title: 'Never Gonna Give You Up',
    thumbnail_url: null,
    creator_id: 'UC123',
    creator_name: 'Rick Astley',
    play_count: 12,
    channel_count: 4,
    last_played_at: '2026-09-21T00:00:00Z',
    active_status: null,
    blocked_kind: null,
    ...overrides,
  }
}

describe('RankingPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getVideoQueueRankings.mockResolvedValue([ranking()])
  })

  it('shows a useful channel ranking without reducing labels to cryptic abbreviations', async () => {
    render(<RankingPanel onAdd={vi.fn()} onBlock={vi.fn()} />)

    const row = await screen.findByRole('listitem')
    expect(within(row).getByText('Never Gonna Give You Up')).toBeInTheDocument()
    expect(within(row).getByText('播放 12 次')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '加入待播' })).toBeInTheDocument()
    expect(getVideoQueueRankings).toHaveBeenCalledWith('channel', 7, undefined)
  })

  it('reloads global 30-day rankings and explains both aggregate metrics', async () => {
    const user = userEvent.setup()
    render(<RankingPanel onAdd={vi.fn()} onBlock={vi.fn()} />)
    await screen.findByRole('listitem')

    await user.click(screen.getByRole('button', { name: '全站' }))
    await user.click(screen.getByRole('button', { name: '30 日' }))

    await waitFor(() =>
      expect(getVideoQueueRankings).toHaveBeenLastCalledWith('global', 30, undefined)
    )
    expect(screen.getByText('4 個頻道 · 播放 12 次')).toBeInTheDocument()
    expect(screen.getByText(/只顯示匿名彙總/)).toBeInTheDocument()
  })

  it('adds an available ranked video and prevents duplicate queue actions', async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn().mockResolvedValue(undefined)
    const { rerender } = render(<RankingPanel onAdd={onAdd} onBlock={vi.fn()} />)
    await user.click(await screen.findByRole('button', { name: '加入待播' }))
    expect(onAdd).toHaveBeenCalledWith(expect.objectContaining({ video_id: 'dQw4w9WgXcQ' }))

    getVideoQueueRankings.mockResolvedValue([ranking({ active_status: 'queued' })])
    rerender(<RankingPanel onAdd={onAdd} onBlock={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: '7 日' }))
    expect(await screen.findByRole('button', { name: '已在待播' })).toBeDisabled()
  })

  it('keeps destructive blocks in a scoped menu and confirms the action', async () => {
    const user = userEvent.setup()
    const onBlock = vi.fn().mockResolvedValue(undefined)
    render(<RankingPanel onAdd={vi.fn()} onBlock={onBlock} />)
    await screen.findByRole('listitem')

    await user.click(screen.getByRole('button', { name: '更多操作' }))
    await user.click(screen.getByRole('menuitem', { name: '封鎖此創作者' }))
    expect(screen.getByText('在此頻道封鎖創作者？')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '封鎖創作者' }))

    expect(onBlock).toHaveBeenCalledWith(
      expect.objectContaining({ video_type: 'youtube', creator_id: 'UC123' }),
      'creator'
    )
  })

  it('shows an actionable retry state instead of a blank ranking', async () => {
    const user = userEvent.setup()
    getVideoQueueRankings.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce([])
    render(<RankingPanel onAdd={vi.fn()} onBlock={vi.fn()} />)

    expect(await screen.findByText('排行暫時載入失敗')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '重新載入' }))
    expect(await screen.findByText('這段期間還沒有有效播放紀錄')).toBeInTheDocument()
  })

  it('uses reusable row skeletons while rankings are loading', () => {
    getVideoQueueRankings.mockReturnValue(new Promise(() => undefined))
    const { container } = render(<RankingPanel onAdd={vi.fn()} onBlock={vi.fn()} />)

    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(6)
  })
})
