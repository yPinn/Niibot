import { describe, expect, it } from 'vitest'

import { splitBilibiliId, watchUrl } from './utils'

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
