import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/errors'
import { __resetReporterState, reportClientError, reportSilent } from '@/lib/clientErrorReporter'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  __resetReporterState()
  fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 202 }))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

const bodyOf = (call: number) =>
  JSON.parse((fetchMock.mock.calls[call][1] as RequestInit).body as string)

describe('reportClientError', () => {
  it('posts to /api/client-errors with keepalive', () => {
    reportClientError({ kind: 'error', message: 'boom once' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/client-errors')
    expect((init as RequestInit).keepalive).toBe(true)
    expect(bodyOf(0)).toMatchObject({
      kind: 'error',
      message: 'boom once',
      fingerprint: expect.any(String),
    })
  })

  it('dedupes the same fingerprint within the window', () => {
    reportClientError({ kind: 'error', message: 'same error' })
    reportClientError({ kind: 'error', message: 'same error' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('normalises volatile ids so near-identical errors share a fingerprint', () => {
    reportClientError({ kind: 'error', message: 'cannot read x at 0xAB12' })
    reportClientError({ kind: 'error', message: 'cannot read x at 0xFF99' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('caps reports per page load', () => {
    for (let i = 0; i < 15; i++) reportClientError({ kind: 'error', message: `distinct ${i}` })
    expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(10)
  })

  it('drops its own failures (stack mentions clientErrorReporter)', () => {
    reportClientError({
      kind: 'error',
      message: 'recursive',
      stack: 'at post (clientErrorReporter.ts:1:1)',
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('skips 401 / 403', () => {
    reportClientError({ kind: 'api', message: 'unauthorized', httpStatus: 401 })
    reportClientError({ kind: 'api', message: 'forbidden', httpStatus: 403 })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('reportSilent', () => {
  it('forwards ApiError fields', () => {
    reportSilent(new ApiError({ message: 'nope', status: 500, code: 'X.Y', requestId: 'req-7' }))
    expect(bodyOf(0)).toMatchObject({
      kind: 'api',
      error_code: 'X.Y',
      http_status: 500,
      request_id: 'req-7',
    })
  })

  it('handles a plain thrown value', () => {
    reportSilent('just a string')
    expect(bodyOf(0)).toMatchObject({ kind: 'api', message: 'just a string' })
  })
})
