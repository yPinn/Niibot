import { describe, expect, it } from 'vitest'

import { liveWatchUrl, requeueText, segmentLabel, splitBilibiliId, watchUrl } from './utils'

describe('watchUrl', () => {
  it('builds a Twitch VOD URL and preserves its start offset', () => {
    expect(watchUrl('twitch_vod', '123456', 90)).toBe('https://www.twitch.tv/videos/123456?t=90s')
  })

  it('omits a zero start offset', () => {
    expect(watchUrl('twitch_vod', '123456', 0)).toBe('https://www.twitch.tv/videos/123456')
  })

  it('builds a bare Bilibili URL for page 1', () => {
    expect(watchUrl('bilibili', 'BV1xx411c7mD')).toBe('https://www.bilibili.com/video/BV1xx411c7mD')
  })

  it('builds a Bilibili URL with ?p= for a multi-part id', () => {
    expect(watchUrl('bilibili', 'BV1xx411c7mD_p2')).toBe(
      'https://www.bilibili.com/video/BV1xx411c7mD?p=2'
    )
  })
})

describe('splitBilibiliId', () => {
  it('treats a bare id as page 1', () => {
    expect(splitBilibiliId('BV1xx411c7mD')).toEqual(['BV1xx411c7mD', 1])
  })

  it('splits a suffixed id into bvid and page', () => {
    expect(splitBilibiliId('BV1xx411c7mD_p3')).toEqual(['BV1xx411c7mD', 3])
  })
})

describe('segments', () => {
  it('carries the start point in watch URLs of seekable platforms', () => {
    expect(watchUrl('youtube', 'dQw4w9WgXcQ', 90)).toBe('https://youtu.be/dQw4w9WgXcQ?t=90')
    expect(watchUrl('bilibili', 'BV1xx411c7mD_p2', 90)).toBe(
      'https://www.bilibili.com/video/BV1xx411c7mD?p=2&t=90'
    )
  })

  it('labels a segment by its start and end', () => {
    expect(segmentLabel({ start_seconds: 90, duration_seconds: 150 })).toBe('1:30–4:00')
    expect(segmentLabel({ start_seconds: 90, duration_seconds: null })).toBe('1:30–')
    expect(segmentLabel({ start_seconds: 0, duration_seconds: 240 })).toBeNull()
  })

  it('re-requests the same segment in chat time syntax', () => {
    const base = { video_type: 'youtube', video_id: 'dQw4w9WgXcQ' }
    expect(requeueText({ ...base, start_seconds: 90, duration_seconds: 150 })).toBe(
      'https://youtu.be/dQw4w9WgXcQ 1:30-4:00'
    )
    expect(requeueText({ ...base, start_seconds: 0, duration_seconds: 240 })).toBe(
      'https://youtu.be/dQw4w9WgXcQ'
    )
  })
})

describe('liveWatchUrl', () => {
  it('links the channel or the live video', () => {
    expect(liveWatchUrl({ source_type: 'twitch_live', source_id: 'lofi' })).toBe(
      'https://www.twitch.tv/lofi'
    )
    expect(liveWatchUrl({ source_type: 'youtube_live', source_id: 'jfKfPfyJRdk' })).toBe(
      'https://youtu.be/jfKfPfyJRdk'
    )
  })
})
