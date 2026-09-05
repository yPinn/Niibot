interface Env {
  API_BACKEND: string
}

const MAX_BODY_BYTES = 10 * 1024 * 1024 // 10 MB
const OVERLAY_STREAM_LEASE_MS = 5 * 60 * 1000

// Anchored so a path segment cannot smuggle in an extra "/stream" suffix or
// traverse past the intended route — exact-equality for the flat Live
// Display route, a pattern for Video Queue's per-username route.
const OVERLAY_STREAM_PATHS = [
  /^\/api\/live-display\/public\/stream$/,
  /^\/api\/video-queue\/public\/[^/]+\/stream$/,
]

export const onRequest: PagesFunction<Env> = async context => {
  const backend = context.env.API_BACKEND
  const url = new URL(context.request.url)
  const target = `${backend}${url.pathname}${url.search}`
  const isOverlayStream =
    context.request.method === 'GET' &&
    OVERLAY_STREAM_PATHS.some(pattern => pattern.test(url.pathname))

  try {
    const headers = new Headers(context.request.headers)
    headers.delete('host')

    const init: RequestInit = {
      method: context.request.method,
      headers,
      redirect: 'manual',
      signal: isOverlayStream
        ? AbortSignal.any([context.request.signal, AbortSignal.timeout(OVERLAY_STREAM_LEASE_MS)])
        : AbortSignal.timeout(15_000),
    }

    if (!['GET', 'HEAD'].includes(context.request.method)) {
      const contentLength = context.request.headers.get('content-length')
      if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
        return Response.json({ error: 'Request body too large' }, { status: 413 })
      }
      init.body = context.request.body
    }

    return await fetch(target, init)
  } catch (e) {
    const isTimeout = e instanceof DOMException && e.name === 'TimeoutError'
    return Response.json(
      { error: isTimeout ? 'Gateway timeout' : 'Bad Gateway' },
      { status: isTimeout ? 504 : 502 }
    )
  }
}
