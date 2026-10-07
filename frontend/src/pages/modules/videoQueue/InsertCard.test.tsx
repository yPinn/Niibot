import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { VideoQueueLiveInsert } from '@/api/videoQueue'

import { InsertCard } from './InsertCard'

const insert: VideoQueueLiveInsert = {
  id: 5,
  source_type: 'twitch_live',
  source_id: 'lofistreamer',
  title: 'beats to relax to',
  creator_name: 'LofiStreamer',
  thumbnail_url: null,
  volume_percent: 30,
  audio_only: false,
  started_at: null,
}

function renderCard(overrides: Partial<Parameters<typeof InsertCard>[0]> = {}) {
  const props = {
    insert: null,
    volumePercent: 30,
    audioOnly: false,
    onStart: vi.fn().mockResolvedValue(undefined),
    onStop: vi.fn().mockResolvedValue(undefined),
    onSaveDefaults: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  }
  render(<InsertCard {...props} />)
  return props
}

describe('InsertCard', () => {
  it('starts an insert from a pasted live URL', async () => {
    const props = renderCard()
    const start = screen.getByRole('button', { name: /開始插播/ })
    expect(start).toBeDisabled()

    await userEvent.type(screen.getByLabelText('直播網址'), ' https://www.twitch.tv/lofistreamer ')
    await userEvent.click(start)
    expect(props.onStart).toHaveBeenCalledWith('https://www.twitch.tv/lofistreamer')
    expect(screen.getByLabelText('直播網址')).toHaveValue('')
  })

  it('shows the running insert with a way to stop it', async () => {
    const props = renderCard({ insert })
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(screen.getByText('LofiStreamer')).toBeInTheDocument()
    expect(screen.getByText('beats to relax to')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '在新分頁開啟直播' })).toHaveAttribute(
      'href',
      'https://www.twitch.tv/lofistreamer'
    )
    expect(screen.queryByLabelText('直播網址')).toBeNull()

    await userEvent.click(screen.getByRole('button', { name: /結束插播/ }))
    expect(props.onStop).toHaveBeenCalled()
  })

  it('saves the insert volume only when it changed and is valid', async () => {
    const props = renderCard()
    const save = screen.getByRole('button', { name: '儲存插播音量' })
    expect(save).toBeDisabled()

    const input = screen.getByLabelText('插播音量')
    await userEvent.clear(input)
    await userEvent.type(input, '150')
    expect(save).toBeDisabled()

    await userEvent.clear(input)
    await userEvent.type(input, '15')
    await userEvent.click(save)
    expect(props.onSaveDefaults).toHaveBeenCalledWith({ insert_volume_percent: 15 })
  })

  it('toggles audio-only right away', async () => {
    const props = renderCard()
    await userEvent.click(screen.getByRole('switch', { name: '僅聲音' }))
    expect(props.onSaveDefaults).toHaveBeenCalledWith({ insert_audio_only: true })
  })
})
