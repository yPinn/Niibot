import { afterEach, describe, expect, it, vi } from 'vitest'

import { requestUrl } from '@/test/requestUrl'

import { getStreamSchedulePublishStatus, retryStreamSchedulePublish } from './streamSchedule'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('stream schedule Twitch publication API', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads status and retries with the explicit mutation header', async () => {
    const value = {
      status: 'pending',
      pending_count: 1,
      synced_count: 0,
      blocked_count: 0,
      error_count: 0,
      last_error_code: null,
      last_synced_at: null,
    }
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(value))
      .mockResolvedValueOnce(jsonResponse({ status: 'queued' }, 202))

    await getStreamSchedulePublishStatus()
    await retryStreamSchedulePublish()

    expect(fetchMock.mock.calls.map(call => requestUrl(call[0]).pathname)).toEqual([
      '/api/stream-schedule/twitch-publish',
      '/api/stream-schedule/twitch-publish/retry',
    ])
    expect(fetchMock.mock.calls[0][1]).toEqual({ credentials: 'include' })
    expect(fetchMock.mock.calls[1][1]).toEqual({
      method: 'POST',
      credentials: 'include',
      headers: { 'X-Niibot-Action': 'stream-schedule-publish-retry' },
    })
  })
})
