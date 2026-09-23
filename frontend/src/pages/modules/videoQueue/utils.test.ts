import { describe, expect, it } from 'vitest'

import { watchUrl } from './utils'

describe('watchUrl', () => {
  it('builds a Twitch VOD URL and preserves its start offset', () => {
    expect(watchUrl('twitch_vod', '123456', 90)).toBe('https://www.twitch.tv/videos/123456?t=90s')
  })

  it('omits a zero start offset', () => {
    expect(watchUrl('twitch_vod', '123456', 0)).toBe('https://www.twitch.tv/videos/123456')
  })
})
