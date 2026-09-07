import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { VideoQueueEntry } from '@/api/videoQueue'

import { NowPlayingCard } from './NowPlayingCard'

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
