/**
 * Unified API error handling.
 *
 * `apiJson` wraps `apiFetch`: on a non-OK response it throws an `ApiError`
 * whose `.message` is the polished zh-TW sentence from the backend envelope
 * (so existing `toast.error(e.message)` call sites keep working), and whose
 * `.code` / `.requestId` let callers branch or let the user report the fault.
 *
 * `apiFetch` itself is unchanged — it still returns a `Response` and is used
 * directly wherever the caller needs the raw response.
 */

import { apiFetch } from '@/api/config'

/** Machine code from the backend, e.g. `TIMER.NOT_FOUND`, `HTTP.500`, or one
 *  of the client-side sentinels below. Never shown to the user. */
export type ApiErrorCode = string

export const NETWORK_ERROR = 'NETWORK'
export const PARSE_ERROR = 'PARSE'

interface Envelope {
  detail?: unknown
  error?: {
    code?: string
    message?: string
    request_id?: string | null
    fields?: Record<string, string> | null
  }
}

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly requestId: string | null
  readonly fields: Record<string, string> | null

  constructor(opts: {
    message: string
    status: number
    code: ApiErrorCode
    requestId?: string | null
    fields?: Record<string, string> | null
  }) {
    super(opts.message)
    this.name = 'ApiError'
    this.status = opts.status
    this.code = opts.code
    this.requestId = opts.requestId ?? null
    this.fields = opts.fields ?? null
  }

  /** 5xx and network failures are worth asking the user to report. */
  get isReportable(): boolean {
    return this.status >= 500 || this.status === 0
  }
}

/** Build an ApiError from a non-OK Response, reading the standard envelope
 *  and falling back through the older `{detail}` / list-detail shapes. */
export async function parseApiError(res: Response, fallback: string): Promise<ApiError> {
  let body: Envelope | null = null
  try {
    body = (await res.clone().json()) as Envelope
  } catch {
    body = null
  }

  const err = body?.error
  const detail = body?.detail
  const message =
    err?.message ||
    (typeof detail === 'string' && detail) ||
    (Array.isArray(detail) &&
      detail.length > 0 &&
      typeof detail[0] === 'object' &&
      detail[0] !== null &&
      'msg' in detail[0] &&
      String((detail[0] as { msg: unknown }).msg)) ||
    res.statusText ||
    fallback

  return new ApiError({
    message: message || fallback,
    status: res.status,
    code: err?.code || `HTTP.${res.status}`,
    requestId: err?.request_id ?? res.headers.get('X-Request-ID'),
    fields: err?.fields ?? null,
  })
}

/**
 * Fetch + parse JSON, throwing a typed ApiError on failure.
 * Use for every endpoint that returns a JSON body and whose errors should
 * surface to the user.
 */
export async function apiJson<T>(
  input: RequestInfo | URL,
  init?: RequestInit,
  opts: { fallback?: string } = {}
): Promise<T> {
  const fallback = opts.fallback ?? '操作失敗，請稍後再試'

  let res: Response
  try {
    res = await apiFetch(input, init)
  } catch {
    throw new ApiError({
      message: '網路連線出了問題，請檢查後再試',
      status: 0,
      code: NETWORK_ERROR,
    })
  }

  if (!res.ok) throw await parseApiError(res, fallback)

  if (res.status === 204) return undefined as T
  try {
    return (await res.json()) as T
  } catch {
    throw new ApiError({ message: fallback, status: res.status, code: PARSE_ERROR })
  }
}

/** Extract a user-facing message from anything thrown, with a fallback. */
export function errorMessage(e: unknown, fallback: string): string {
  if (e instanceof Error && e.message) return e.message
  return fallback
}
