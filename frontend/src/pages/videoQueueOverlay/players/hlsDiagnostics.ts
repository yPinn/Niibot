import { reportClientError } from '@/lib/clientErrorReporter'

/** The subset of hls.js's ERROR event data worth reporting. */
export interface HlsErrorData {
  type?: string
  details?: string
  url?: string
  response?: { code?: number }
}

/**
 * Report a fatal hls.js error to client-error telemetry (admin → Monitor →
 * Errors), so a Twitch VOD / live stream that falls back to the embed can be
 * diagnosed without a debugger in OBS. Carries the failing *host* only — the
 * playlist URLs are signed — plus hls.js's error type/details and the HTTP code.
 */
export function reportHlsFailure(
  source: 'twitch_vod' | 'twitch_live',
  data: HlsErrorData,
  phase: 'start' | 'playing'
): void {
  let host = ''
  try {
    host = data.url ? new URL(data.url, window.location.href).host : ''
  } catch {
    /* ignore */
  }
  reportClientError({
    kind: 'error',
    message: `hls ${source} ${phase}: ${data.type ?? '?'}/${data.details ?? '?'}${host ? ` @${host}` : ''}`,
    errorCode: 'VIDEO_QUEUE.HLS_FAILED',
    httpStatus: data.response?.code ?? null,
  })
}
