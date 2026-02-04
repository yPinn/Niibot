interface Env {
  API_BACKEND: string
}

export const onRequest: PagesFunction<Env> = async context => {
  const backend = context.env.API_BACKEND
  const url = new URL(context.request.url)
  const target = `${backend}${url.pathname}${url.search}`

  try {
    const init: RequestInit = {
      method: context.request.method,
      headers: context.request.headers,
      redirect: 'follow',
    }

    if (!['GET', 'HEAD'].includes(context.request.method)) {
      init.body = context.request.body
    }

    return fetch(target, init)
  } catch (e) {
    return Response.json({ error: String(e), target }, { status: 502 })
  }
}
