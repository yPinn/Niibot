import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/api/streamSchedule', () => ({
  searchStreamScheduleGames: vi.fn(),
}))

import { searchStreamScheduleGames } from '@/api/streamSchedule'

import { GamePicker, type GameValue } from './GamePicker'

const mockSearch = vi.mocked(searchStreamScheduleGames)

function Harness({ initial }: { initial: GameValue | null }) {
  return <GamePicker value={initial} onChange={vi.fn()} />
}

describe('GamePicker', () => {
  beforeEach(() => {
    mockSearch.mockReset()
    // A component mounted with a value always fires one box-art backfill
    // search (see GamePicker's "one-shot backfill" effect) — default it to
    // an empty match so tests that aren't exercising that path don't crash.
    mockSearch.mockResolvedValue([])
  })

  it('searches (debounced) as the user types and lists matches', async () => {
    mockSearch.mockResolvedValue([{ id: '509658', name: 'Just Chatting', box_art_url: null }])
    const user = userEvent.setup()
    render(<Harness initial={null} />)

    await user.type(screen.getByPlaceholderText('搜尋 Twitch 遊戲分類…'), 'just chat')

    await waitFor(() => expect(mockSearch).toHaveBeenCalledWith('just chat'))
    expect(await screen.findByText('Just Chatting')).toBeInTheDocument()
  })

  it('selecting a result calls onChange with the picked id/name and fills the input', async () => {
    mockSearch.mockResolvedValue([{ id: '509658', name: 'Just Chatting', box_art_url: null }])
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<GamePicker value={null} onChange={onChange} />)

    const input = screen.getByPlaceholderText('搜尋 Twitch 遊戲分類…')
    await user.type(input, 'just')
    const option = await screen.findByText('Just Chatting')
    await user.click(option)

    expect(onChange).toHaveBeenCalledWith({ id: '509658', name: 'Just Chatting' })
    expect(input).toHaveValue('Just Chatting')
  })

  it('shows a clear button once a game is selected, which clears the value', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(<GamePicker value={{ id: '509658', name: 'Just Chatting' }} onChange={onChange} />)

    await user.click(screen.getByRole('button', { name: '清除遊戲分類' }))

    expect(onChange).toHaveBeenCalledWith(null)
    expect(screen.getByPlaceholderText('搜尋 Twitch 遊戲分類…')).toHaveValue('')
  })

  it('does not run the debounced search just from focusing an already-selected value', async () => {
    const user = userEvent.setup()
    render(<GamePicker value={{ id: '509658', name: 'Just Chatting' }} onChange={vi.fn()} />)
    // The one-shot box-art backfill search on mount is expected; wait for it
    // to settle before asserting nothing further gets triggered by focus alone.
    await waitFor(() => expect(mockSearch).toHaveBeenCalledTimes(1))

    await user.click(screen.getByPlaceholderText('搜尋 Twitch 遊戲分類…'))
    // Give the debounce window a chance to fire if it incorrectly would.
    await new Promise(resolve => setTimeout(resolve, 400))

    expect(mockSearch).toHaveBeenCalledTimes(1)
  })

  it('shows box art thumbnails in the dropdown so a look-alike category is not picked by mistake', async () => {
    mockSearch.mockResolvedValue([
      {
        id: '509658',
        name: 'Just Chatting',
        box_art_url: 'https://x/509658-{width}x{height}.jpg',
      },
    ])
    const user = userEvent.setup()
    const { container } = render(<Harness initial={null} />)

    await user.type(screen.getByPlaceholderText('搜尋 Twitch 遊戲分類…'), 'just chat')
    await screen.findByText('Just Chatting')

    const thumb = container.querySelector('img[src*="509658-32x43.jpg"]')
    expect(thumb).not.toBeNull()
  })

  it('backfills box art for a value it was mounted with, once the lookup resolves', async () => {
    mockSearch.mockResolvedValue([
      {
        id: '509658',
        name: 'Just Chatting',
        box_art_url: 'https://x/509658-{width}x{height}.jpg',
      },
    ])
    const { container } = render(
      <GamePicker value={{ id: '509658', name: 'Just Chatting' }} onChange={vi.fn()} />
    )

    await waitFor(() => {
      expect(container.querySelector('img[src*="509658-24x32.jpg"]')).not.toBeNull()
    })
    expect(mockSearch).toHaveBeenCalledWith('Just Chatting')
  })
})
