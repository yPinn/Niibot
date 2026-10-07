import { describe, expect, it, vi } from 'vitest'

import { reportClientError } from '@/lib/clientErrorReporter'

import { reportHlsFailure } from './hlsDiagnostics'

vi.mock('@/lib/clientErrorReporter', () => ({ reportClientError: vi.fn() }))

describe('reportHlsFailure', () => {
  it('reports type, details, host and status — never the signed URL', () => {
    reportHlsFailure(
      'twitch_vod',
      {
        type: 'networkError',
        details: 'levelLoadError',
        url: 'https://d1m7jfoe9zdc1j.cloudfront.net/abc/chunked/index-dvr.m3u8?sig=secret',
        response: { code: 403 },
      },
      'start'
    )
    const input = vi.mocked(reportClientError).mock.calls[0][0]
    expect(input.message).toBe(
      'hls twitch_vod start: networkError/levelLoadError @d1m7jfoe9zdc1j.cloudfront.net'
    )
    expect(input.message).not.toContain('secret')
    expect(input).toMatchObject({ errorCode: 'VIDEO_QUEUE.HLS_FAILED', httpStatus: 403 })
  })
})
