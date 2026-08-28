/**
 * Frontend error telemetry — ships to POST /api/client-errors.
 *
 * Wired to window.onerror / unhandledrejection (via initClientErrorReporting)
 * and to the ErrorBoundary. Also exposes reportSilent() for the api-layer
 * catch sites that swallow an error and return a sentinel value.
 *
 * Rules: dedupe by fingerprint (30s), cap 10 per page load, never report
 * the reporter's own failures, and skip 401/403 (normal auth flow).
 */

import { API_ENDPOINTS } from '@/api/config'
import { ApiError } from '@/api/errors'

type Kind = 'error' | 'unhandledrejection' | 'react' | 'api'

interface ReportInput {
  kind: Kind
  message: string
  stack?: string | null
  componentStack?: string | null
  errorCode?: string | null
  httpStatus?: number | null
  requestId?: string | null
}

const APP_VERSION = (import.meta.env.VITE_APP_VERSION as string | undefined) ?? 'dev'
const DEDUPE_MS = 30_000
const MAX_PER_PAGE = 10

const seen = new Map<string, number>()
let sentThisPage = 0
let initialised = false

/** test-only: clear the per-page dedupe/counter state */
export function __resetReporterState(): void {
  seen.clear()
  sentThisPage = 0
  initialised = false
}

/** cheap synchronous string hash (djb2) — only needs to be stable, not secure */
function hash(s: string): string {
  let h = 5381
  for (let i = 0; i < s.length; i++) h = (h * 33) ^ s.charCodeAt(i)
  return (h >>> 0).toString(36)
}

function topFrame(stack?: string | null): string {
  if (!stack) return ''
  const line = stack.split('\n').find(l => /\bat\b|@/.test(l))
  return (line ?? '').trim().replace(/:\d+:\d+\)?$/, '')
}

/** strip volatile bits so "the same bug" fingerprints identically */
function normalize(msg: string): string {
  return msg
    .replace(/\b0x[0-9a-f]+\b/gi, '0xN')
    .replace(/\b\d{2,}\b/g, 'N')
    .replace(/https?:\/\/\S+/g, 'URL')
    .slice(0, 300)
}

function shouldDrop(input: ReportInput): boolean {
  if (sentThisPage >= MAX_PER_PAGE) return true
  // the reporter must never report itself (note: not '.test.ts')
  if (/clientErrorReporter\.[jt]s:/.test(input.stack ?? '')) return true
  if (input.httpStatus === 401 || input.httpStatus === 403) return true
  return false
}

function post(payload: Record<string, unknown>): void {
  const body = JSON.stringify(payload)
  try {
    void fetch(API_ENDPOINTS.clientErrors, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body,
      keepalive: true,
      credentials: 'include',
    }).catch(() => {}) // a failed report is not itself reportable
  } catch {
    /* ignore */
  }
}

export function reportClientError(input: ReportInput): void {
  try {
    if (shouldDrop(input)) return

    const fp = hash(`${input.kind}|${normalize(input.message)}|${topFrame(input.stack)}`)
    const now = Date.now()
    const last = seen.get(fp)
    if (last && now - last < DEDUPE_MS) return
    seen.set(fp, now)
    sentThisPage++

    post({
      kind: input.kind,
      fingerprint: fp,
      message: input.message.slice(0, 2000),
      stack: input.stack?.slice(0, 8000) ?? null,
      component_stack: input.componentStack?.slice(0, 4000) ?? null,
      url: window.location.href.slice(0, 2000),
      route: window.location.pathname.slice(0, 200),
      request_id: input.requestId ?? null,
      error_code: input.errorCode ?? null,
      http_status: input.httpStatus ?? null,
      app_version: APP_VERSION,
    })
  } catch {
    /* telemetry must never break the app */
  }
}

/** For api-layer sites that catch an error and return a sentinel value. */
export function reportSilent(e: unknown): void {
  if (e instanceof ApiError) {
    reportClientError({
      kind: 'api',
      message: e.message,
      stack: e.stack,
      errorCode: e.code,
      httpStatus: e.status,
      requestId: e.requestId,
    })
    return
  }
  const err = e instanceof Error ? e : null
  reportClientError({
    kind: 'api',
    message: err?.message ?? String(e),
    stack: err?.stack ?? null,
  })
}

export function initClientErrorReporting(): void {
  if (typeof window === 'undefined' || initialised) return
  initialised = true

  window.addEventListener('error', ev => {
    // resource-load errors have no `.error` and a useless message — skip
    if (!ev.error && !ev.message) return
    reportClientError({
      kind: 'error',
      message: ev.message || String(ev.error),
      stack: ev.error?.stack ?? null,
    })
  })

  window.addEventListener('unhandledrejection', ev => {
    const reason = ev.reason
    if (reason instanceof ApiError) {
      reportClientError({
        kind: 'unhandledrejection',
        message: reason.message,
        stack: reason.stack,
        errorCode: reason.code,
        httpStatus: reason.status,
        requestId: reason.requestId,
      })
      return
    }
    const err = reason instanceof Error ? reason : null
    reportClientError({
      kind: 'unhandledrejection',
      message: err?.message ?? String(reason),
      stack: err?.stack ?? null,
    })
  })
}
