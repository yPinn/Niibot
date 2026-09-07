import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { VideoQueueHistoryEntry } from '@/api/videoQueue'

import { HistoryTable } from './HistoryTable'

function entry(overrides: Partial<VideoQueueHistoryEntry> = {}): VideoQueueHistoryEntry {
  return {
    id: 1,
    video_id: 'abc',
    title: 'A clip',
    duration_seconds: 42,
    requested_by: 'viewer',
    source: 'chat',
    video_type: 'youtube',
    status: 'done',
    started_at: null,
    ended_at: new Date().toISOString(),
    ...overrides,
  }
}

const noop = () => {}

describe('HistoryTable', () => {
  it('shows the empty state with no entries', () => {
    render(
      <HistoryTable
        entries={[]}
        hasMore={false}
        loadingMore={false}
        onLoadMore={noop}
        onRequeue={noop}
        onBlock={noop}
      />
    )
    expect(screen.getByText('尚無播放紀錄')).toBeInTheDocument()
  })

  it('renders status per entry and calls onRequeue with the row', async () => {
    const onRequeue = vi.fn()
    render(
      <HistoryTable
        entries={[entry({ id: 7, status: 'skipped', title: 'Skipped one' })]}
        hasMore={false}
        loadingMore={false}
        onLoadMore={noop}
        onRequeue={onRequeue}
        onBlock={noop}
      />
    )
    expect(screen.getByText('略過')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重新點播' }))
    expect(onRequeue).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
  })

  it('calls onBlock with the row', async () => {
    const onBlock = vi.fn()
    render(
      <HistoryTable
        entries={[entry({ id: 9 })]}
        hasMore={false}
        loadingMore={false}
        onLoadMore={noop}
        onRequeue={noop}
        onBlock={onBlock}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))
    expect(onBlock).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }))
  })

  it('shows "load more" only when hasMore', () => {
    const { rerender } = render(
      <HistoryTable
        entries={[entry()]}
        hasMore={false}
        loadingMore={false}
        onLoadMore={noop}
        onRequeue={noop}
        onBlock={noop}
      />
    )
    expect(screen.queryByRole('button', { name: '載入更多' })).not.toBeInTheDocument()
    rerender(
      <HistoryTable
        entries={[entry()]}
        hasMore
        loadingMore={false}
        onLoadMore={noop}
        onRequeue={noop}
        onBlock={noop}
      />
    )
    expect(screen.getByRole('button', { name: '載入更多' })).toBeInTheDocument()
  })
})
