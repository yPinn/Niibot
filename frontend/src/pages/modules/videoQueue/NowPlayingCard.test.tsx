import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { VideoQueueEntry, VideoQueueLiveInsert } from '@/api/videoQueue'

import { NowPlayingCard, type PlayComposer } from './NowPlayingCard'

function entry(overrides: Partial<VideoQueueEntry> = {}): VideoQueueEntry {
  return {
    id: 1,
    video_id: 'abc',
    title: 'A video',
    duration_seconds: 100,
    is_vertical: false,
    thumbnail_url: null,
    start_seconds: 0,
    requested_by: 'viewer',
    source: 'chat',
    video_type: 'bilibili',
    started_at: null,
    ...overrides,
  }
}

const noop = () => {}

describe('NowPlayingCard thumbnail', () => {
  it('preserves the Twitch VOD start offset in the external link', () => {
    render(
      <NowPlayingCard
        current={entry({ video_type: 'twitch_vod', video_id: '123456', start_seconds: 90 })}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )

    expect(screen.getByRole('link', { name: '在新分頁開啟影片' })).toHaveAttribute(
      'href',
      'https://www.twitch.tv/videos/123456?t=90s'
    )
  })

  it('renders the fetched poster when thumbnail_url is set', () => {
    render(
      <NowPlayingCard
        current={entry({ thumbnail_url: 'https://i0.hdslb.com/x.jpg' })}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )
    const img = screen.getByRole('presentation') as HTMLImageElement
    expect(img.src).toBe('https://i0.hdslb.com/x.jpg')
    expect(img.getAttribute('referrerpolicy')).toBe('no-referrer')
  })

  it('falls back to a deterministic thumbnail for YouTube rows with no stored url', () => {
    render(
      <NowPlayingCard
        current={entry({ video_type: 'youtube', video_id: 'dQw4w9WgXcQ', thumbnail_url: null })}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )
    expect((screen.getByRole('presentation') as HTMLImageElement).src).toContain(
      'i.ytimg.com/vi/dQw4w9WgXcQ'
    )
  })

  it('shows the placeholder for a non-YouTube row with no thumbnail, and after an image error', () => {
    const { rerender } = render(
      <NowPlayingCard
        current={entry({ thumbnail_url: null, video_type: 'twitch_clip' })}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )
    expect(screen.queryByRole('presentation')).toBeNull()

    rerender(
      <NowPlayingCard
        current={entry({ thumbnail_url: 'https://i0.hdslb.com/broken.jpg' })}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )
    fireEvent.error(screen.getByRole('presentation'))
    expect(screen.queryByRole('presentation')).toBeNull()
  })
})

const liveInsert: VideoQueueLiveInsert = {
  id: 5,
  source_type: 'twitch_live',
  source_id: 'lofistreamer',
  title: 'beats to relax to',
  creator_name: 'LofiStreamer',
  thumbnail_url: null,
  volume_percent: 30,
  audio_only: true,
  started_at: null,
}

function composer(overrides: Partial<PlayComposer> = {}): PlayComposer {
  return {
    url: '',
    onUrlChange: vi.fn(),
    onAdd: vi.fn(),
    onInsert: vi.fn(),
    busy: null,
    ...overrides,
  }
}

describe('NowPlayingCard live insert and composer', () => {
  it('shows the insert instead of the queue entry, with stop instead of skip', () => {
    const onStopInsert = vi.fn()
    render(
      <NowPlayingCard
        current={entry()}
        insert={liveInsert}
        onStopInsert={onStopInsert}
        queueSize={2}
        totalQueuedDuration={null}
        onSkip={noop}
      />
    )
    expect(screen.getByText('LIVE')).toBeInTheDocument()
    expect(screen.getByText('LofiStreamer')).toBeInTheDocument()
    expect(screen.getByText('直播插播中，佇列暫停 · 僅聲音')).toBeInTheDocument()
    expect(screen.getByText('插播結束後')).toBeInTheDocument()
    expect(screen.queryByText('A video')).toBeNull()
    expect(screen.queryByRole('button', { name: /跳過/ })).toBeNull()
    expect(screen.getByRole('link', { name: '在新分頁開啟直播' })).toHaveAttribute(
      'href',
      'https://www.twitch.tv/lofistreamer'
    )
    fireEvent.click(screen.getByRole('button', { name: /結束插播/ }))
    expect(onStopInsert).toHaveBeenCalled()
  })

  it('one input queues on Enter / 加入 and inserts on 插播', () => {
    const c = composer({ url: 'https://youtu.be/x 1:30-4:00' })
    render(
      <NowPlayingCard
        current={null}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
        composer={c}
      />
    )
    fireEvent.submit(screen.getByLabelText('影片或直播網址'))
    expect(c.onAdd).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: /插播/ }))
    expect(c.onInsert).toHaveBeenCalledTimes(1)
  })

  it('disables both actions while empty or busy, and says 換台 during an insert', () => {
    const { rerender } = render(
      <NowPlayingCard
        current={null}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
        composer={composer()}
      />
    )
    expect(screen.getByRole('button', { name: /加入/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /插播/ })).toBeDisabled()

    rerender(
      <NowPlayingCard
        current={null}
        insert={liveInsert}
        queueSize={0}
        totalQueuedDuration={null}
        onSkip={noop}
        composer={composer({ url: 'https://www.twitch.tv/other', busy: 'insert' })}
      />
    )
    expect(screen.getByRole('button', { name: /換台/ })).toBeDisabled()
    expect(screen.getByRole('button', { name: /加入/ })).toBeDisabled()
  })
})
