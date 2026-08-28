import { afterEach, describe, expect, it, vi } from 'vitest'

import { ApiError, apiJson, errorMessage, parseApiError } from '@/api/errors'

afterEach(() => vi.restoreAllMocks())

const res = (body: unknown, init: ResponseInit = {}) =>
  new Response(typeof body === 'string' ? body : JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })

describe('parseApiError', () => {
  it('reads the new envelope', async () => {
    const r = res(
      {
        detail: '找不到這個計時器',
        error: { code: 'TIMER.NOT_FOUND', message: '找不到這個計時器', request_id: 'req-1' },
      },
      { status: 404 }
    )
    const e = await parseApiError(r, 'fallback')
    expect(e.message).toBe('找不到這個計時器')
    expect(e.code).toBe('TIMER.NOT_FOUND')
    expect(e.requestId).toBe('req-1')
    expect(e.status).toBe(404)
  })

  it('falls back to a plain {detail} string', async () => {
    const r = res({ detail: 'Timer not found' }, { status: 404 })
    const e = await parseApiError(r, 'fallback')
    expect(e.message).toBe('Timer not found')
    expect(e.code).toBe('HTTP.404')
  })

  it('handles a list-shaped detail without producing [object Object]', async () => {
    const r = res({ detail: [{ loc: ['body', 'x'], msg: 'field required' }] }, { status: 422 })
    const e = await parseApiError(r, 'fallback')
    expect(e.message).toBe('field required')
    expect(e.message).not.toContain('[object Object]')
  })

  it('uses the fallback when the body is not JSON', async () => {
    const r = new Response('<html>502</html>', { status: 502 })
    const e = await parseApiError(r, '系統忙碌中')
    expect(e.message).toBe('系統忙碌中')
    expect(e.status).toBe(502)
    expect(e.isReportable).toBe(true)
  })

  it('reads request id from the header when absent from the body', async () => {
    const r = res({ detail: 'x' }, { status: 500, headers: { 'X-Request-ID': 'hdr-9' } })
    const e = await parseApiError(r, 'f')
    expect(e.requestId).toBe('hdr-9')
  })
})

describe('apiJson', () => {
  it('returns the parsed body on 200', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res({ ok: true })))
    await expect(apiJson('/x')).resolves.toEqual({ ok: true })
  })

  it('throws an ApiError on a non-OK response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(res({ detail: 'nope' }, { status: 400 })))
    await expect(apiJson('/x')).rejects.toBeInstanceOf(ApiError)
  })

  it('throws a NETWORK ApiError when fetch rejects', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))
    await expect(apiJson('/x')).rejects.toMatchObject({ code: 'NETWORK', status: 0 })
  })

  it('returns undefined for 204', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 204 })))
    await expect(apiJson('/x')).resolves.toBeUndefined()
  })
})

describe('errorMessage', () => {
  it('prefers an Error message', () => {
    expect(errorMessage(new Error('boom'), 'fb')).toBe('boom')
  })
  it('falls back for non-errors', () => {
    expect(errorMessage('nope', 'fb')).toBe('fb')
  })
})
