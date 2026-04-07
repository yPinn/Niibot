interface Env {
  API_BACKEND: string
}

const MAX_BODY_BYTES = 10 * 1024 * 1024 // 10 MB

export const onRequest: PagesFunction<Env> = async context => {
  const backend = context.env.API_BACKEND
  const url = new URL(context.request.url)
  const target = `${backend}${url.pathname}${url.search}`

  try {
    const headers = new Headers(context.request.headers)
    headers.delete('host')

    const init: RequestInit = {
      method: context.request.method,
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(15_000),
    }

    if (!['GET', 'HEAD'].includes(context.request.method)) {
      const contentLength = context.request.headers.get('content-length')
      if (contentLength && parseInt(contentLength, 10) > MAX_BODY_BYTES) {
        return Response.json({ error: 'Request body too large' }, { status: 413 })
      }
      init.body = context.request.body
    }

    return fetch(target, init)
  } catch (e) {
    const isTimeout = e instanceof DOMException && e.name === 'TimeoutError'
    return Response.json(
      { error: isTimeout ? 'Gateway timeout' : 'Bad Gateway' },
      { status: isTimeout ? 504 : 502 }
    )
  }
}
