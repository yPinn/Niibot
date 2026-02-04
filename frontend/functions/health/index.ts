interface Env {
  API_BACKEND: string
}

export const onRequest: PagesFunction<Env> = async context => {
  return fetch(`${context.env.API_BACKEND}/health`)
}
