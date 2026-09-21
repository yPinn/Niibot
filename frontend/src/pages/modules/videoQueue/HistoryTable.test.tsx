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
    start_seconds: 0,
    requested_by: 'viewer',
    requested_by_id: null,
    source: 'chat',
    video_type: 'youtube',
    status: 'done',
    started_at: null,
    ended_at: new Date().toISOString(),
    creator_id: null,
    creator_name: null,
    ...overrides,
  }
}

const noop = () => {}

describe('HistoryTable', () => {
  it('shows the empty state with no entries', () => {
    render(<HistoryTable entries={[]} onRequeue={noop} onBlock={noop} />)
    expect(screen.getByText('尚無播放紀錄')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('renders status per entry and calls onRequeue with the row', async () => {
    const onRequeue = vi.fn()
    render(
      <HistoryTable
        entries={[entry({ id: 7, status: 'skipped', title: 'Skipped one' })]}
        onRequeue={onRequeue}
        onBlock={noop}
      />
    )
    expect(screen.getByText('略過')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '重新點播' }))
    expect(onRequeue).toHaveBeenCalledWith(expect.objectContaining({ id: 7 }))
  })

  it('opens a menu and calls onBlock with the chosen kind', async () => {
    const onBlock = vi.fn()
    render(<HistoryTable entries={[entry({ id: 9 })]} onRequeue={noop} onBlock={onBlock} />)
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: '封鎖此影片' }))
    expect(onBlock).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }), 'video')
  })

  it('disables blocking the creator when the entry has no creator_id', async () => {
    render(<HistoryTable entries={[entry({ creator_id: null })]} onRequeue={noop} onBlock={noop} />)
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))
    expect(await screen.findByRole('menuitem', { name: '封鎖此創作者' })).toHaveAttribute(
      'aria-disabled',
      'true'
    )
  })

  it('calls onBlock with kind creator when the entry has a creator_id', async () => {
    const onBlock = vi.fn()
    render(
      <HistoryTable
        entries={[entry({ creator_id: 'UC123', creator_name: 'Some Channel' })]}
        onRequeue={noop}
        onBlock={onBlock}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))
    await userEvent.click(await screen.findByRole('menuitem', { name: '封鎖此創作者' }))
    expect(onBlock).toHaveBeenCalledWith(
      expect.objectContaining({ creator_id: 'UC123' }),
      'creator'
    )
  })
})
