import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { EmoteItem, OtherChannelEmotes } from '@/api/emotes'

import { EmoteInserter } from './EmoteInserter'

function makeEmote(overrides: Partial<EmoteItem> = {}): EmoteItem {
  return {
    id: 'e1',
    name: 'Kappa',
    url: 'https://cdn.example.com/e1.png',
    emote_type: 'globals',
    tier: '',
    available: true,
    animated: false,
    ...overrides,
  }
}

function makeOtherChannel(overrides: Partial<OtherChannelEmotes> = {}): OtherChannelEmotes {
  return {
    channel_id: 'other-1',
    channel_name: 'otherchannel',
    display_name: 'OtherChannel',
    avatar: 'https://img.example.com/other-1.png',
    emotes: [makeEmote({ id: 'oe1', name: 'OtherSub' })],
    ...overrides,
  }
}

describe('EmoteInserter', () => {
  it('inserts the emote name with a trailing space when clicked', async () => {
    const onInsert = vi.fn()
    render(<EmoteInserter emotes={[makeEmote({ name: 'PogChamp' })]} onInsert={onInsert} />)

    await userEvent.click(screen.getByRole('button', { name: 'PogChamp' }))

    expect(onInsert).toHaveBeenCalledWith('PogChamp ')
  })

  it('hides unavailable emotes silently, with no "N hidden" message', () => {
    render(
      <EmoteInserter
        emotes={[
          makeEmote({ id: 'e1', name: 'Available', available: true }),
          makeEmote({ id: 'e2', name: 'Blocked', available: false }),
          makeEmote({ id: 'e3', name: 'AlsoBlocked', available: false }),
        ]}
        onInsert={vi.fn()}
      />
    )

    expect(screen.getByRole('button', { name: 'Available' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Blocked' })).not.toBeInTheDocument()
    expect(screen.queryByText(/未顯示/)).not.toBeInTheDocument()
  })

  it('renders nothing when there are no available emotes', () => {
    const { container } = render(
      <EmoteInserter emotes={[makeEmote({ available: false })]} onInsert={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a loading message instead of chips while loading', () => {
    render(<EmoteInserter emotes={[]} onInsert={vi.fn()} loading />)
    expect(screen.getByText(/載入中/)).toBeInTheDocument()
  })

  it('shows the error message instead of chips on error', () => {
    render(<EmoteInserter emotes={[makeEmote()]} onInsert={vi.fn()} error="載入表情符號失敗" />)
    expect(screen.getByText('載入表情符號失敗')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Kappa' })).not.toBeInTheDocument()
  })

  it('renders an other-channel group collapsed, hiding its emotes until expanded', async () => {
    const onInsert = vi.fn()
    render(<EmoteInserter emotes={[]} otherChannels={[makeOtherChannel()]} onInsert={onInsert} />)

    expect(screen.getByText('OtherChannel')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'OtherSub' })).not.toBeInTheDocument()

    await userEvent.click(screen.getByText('OtherChannel'))

    const chip = screen.getByRole('button', { name: 'OtherSub' })
    expect(chip).toBeInTheDocument()
    await userEvent.click(chip)
    expect(onInsert).toHaveBeenCalledWith('OtherSub ')
  })

  it('still renders when there are no current-channel emotes but other channels exist', () => {
    const { container } = render(
      <EmoteInserter emotes={[]} otherChannels={[makeOtherChannel()]} onInsert={vi.fn()} />
    )
    expect(container).not.toBeEmptyDOMElement()
  })

  it("separates this channel's own emotes from Twitch globals into labelled groups", () => {
    render(
      <EmoteInserter
        emotes={[
          makeEmote({ id: 'e1', name: 'ChannelFollow', emote_type: 'follower' }),
          makeEmote({ id: 'e2', name: 'ChannelSub', emote_type: 'subscriptions' }),
          makeEmote({ id: 'e3', name: 'Kappa', emote_type: 'globals' }),
        ]}
        onInsert={vi.fn()}
      />
    )

    const channelLabel = screen.getByText('本頻道貼圖')
    const globalLabel = screen.getByText('全球貼圖')
    expect(channelLabel).toBeInTheDocument()
    expect(globalLabel).toBeInTheDocument()

    // Both channel emotes sit under the channel label, not the global one.
    const channelGroup = channelLabel.parentElement!
    expect(within(channelGroup).getByRole('button', { name: 'ChannelFollow' })).toBeInTheDocument()
    expect(within(channelGroup).queryByRole('button', { name: 'Kappa' })).not.toBeInTheDocument()

    const globalGroup = globalLabel.parentElement!
    expect(within(globalGroup).getByRole('button', { name: 'Kappa' })).toBeInTheDocument()
    expect(
      within(globalGroup).queryByRole('button', { name: 'ChannelFollow' })
    ).not.toBeInTheDocument()
  })

  it('omits the global-emote label entirely when the channel has no globals available', () => {
    render(
      <EmoteInserter
        emotes={[makeEmote({ id: 'e1', name: 'ChannelFollow', emote_type: 'follower' })]}
        onInsert={vi.fn()}
      />
    )

    expect(screen.getByText('本頻道貼圖')).toBeInTheDocument()
    expect(screen.queryByText('全球貼圖')).not.toBeInTheDocument()
  })
})
