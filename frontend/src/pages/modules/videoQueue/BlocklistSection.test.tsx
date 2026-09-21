import { createRef } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { BlocklistEntry } from '@/api/videoQueue'

import { BlocklistSection, type BlocklistSectionHandle } from './BlocklistSection'

const getVideoQueueBlocklist = vi.fn<() => Promise<BlocklistEntry[]>>()
const addVideoQueueBlock = vi.fn()
const removeVideoQueueBlock = vi.fn()

vi.mock('@/api/videoQueue', () => ({
  getVideoQueueBlocklist: () => getVideoQueueBlocklist(),
  addVideoQueueBlock: (...a: unknown[]) => addVideoQueueBlock(...a),
  removeVideoQueueBlock: (...a: unknown[]) => removeVideoQueueBlock(...a),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

function block(overrides: Partial<BlocklistEntry> = {}): BlocklistEntry {
  return { id: 1, kind: 'keyword', value: 'lofi', label: null, created_at: null, ...overrides }
}

describe('BlocklistSection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getVideoQueueBlocklist.mockResolvedValue([])
  })

  it('lists existing entries', async () => {
    getVideoQueueBlocklist.mockResolvedValue([block({ id: 3, kind: 'user', value: 'spammer' })])
    render(<BlocklistSection />)
    expect(await screen.findByText('spammer')).toBeInTheDocument()
    expect(screen.getByText('點播者')).toBeInTheDocument()
  })

  it('uses row skeletons while the blocklist is loading', () => {
    getVideoQueueBlocklist.mockReturnValue(new Promise(() => undefined))
    const { container } = render(<BlocklistSection />)

    expect(container.querySelectorAll('[data-slot="skeleton"]')).toHaveLength(3)
    expect(screen.queryByText('尚無封鎖項目')).not.toBeInTheDocument()
  })

  it('fills the available list area with the shared empty state', async () => {
    const { container } = render(<BlocklistSection />)

    expect(await screen.findByText('尚無封鎖項目')).toBeInTheDocument()
    expect(container.querySelector('[data-slot="empty"]')).toBeInTheDocument()
  })

  it('adds a rule and prepends it', async () => {
    addVideoQueueBlock.mockResolvedValue(block({ id: 5, kind: 'keyword', value: 'drama' }))
    render(<BlocklistSection />)
    await screen.findByText('尚無封鎖項目')

    await userEvent.type(screen.getByPlaceholderText('標題關鍵字'), 'drama')
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))

    expect(addVideoQueueBlock).toHaveBeenCalledWith('keyword', 'drama', undefined)
    expect(await screen.findByText('drama')).toBeInTheDocument()
  })

  it('extracts a YouTube id when blocking a video URL', async () => {
    addVideoQueueBlock.mockResolvedValue(block({ id: 8, kind: 'video', value: 'dQw4w9WgXcQ' }))
    render(<BlocklistSection />)
    await screen.findByText('尚無封鎖項目')

    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.click(screen.getByRole('option', { name: '影片' }))
    await userEvent.type(
      screen.getByPlaceholderText('影片 ID 或連結'),
      'https://youtube.com/watch?v=dQw4w9WgXcQ'
    )
    await userEvent.click(screen.getByRole('button', { name: '封鎖' }))

    expect(addVideoQueueBlock).toHaveBeenCalledWith('video', 'dQw4w9WgXcQ', undefined, 'youtube')
  })

  it('removes a rule optimistically', async () => {
    getVideoQueueBlocklist.mockResolvedValue([block({ id: 2, value: 'nope' })])
    removeVideoQueueBlock.mockResolvedValue(undefined)
    render(<BlocklistSection />)
    await screen.findByText('nope')

    await userEvent.click(screen.getByRole('button', { name: '移除' }))
    await waitFor(() => expect(screen.queryByText('nope')).not.toBeInTheDocument())
    expect(removeVideoQueueBlock).toHaveBeenCalledWith(2)
  })

  it('exposes addBlock through its ref', async () => {
    addVideoQueueBlock.mockResolvedValue(
      block({ id: 9, kind: 'video', value: 'vid', label: 'A title' })
    )
    const ref = createRef<BlocklistSectionHandle>()
    render(<BlocklistSection ref={ref} />)
    await screen.findByText('尚無封鎖項目')

    await ref.current!.addBlock('video', 'vid', 'A title')
    expect(addVideoQueueBlock).toHaveBeenCalledWith('video', 'vid', 'A title')
    expect(await screen.findByText('A title')).toBeInTheDocument()
  })
})
