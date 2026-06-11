/**
 * Edge middleware: dynamic Open Graph / Twitter meta for public, per-channel
 * pages. The app is a client-rendered SPA, so social crawlers (Discord,
 * Twitter, LINE, Facebook…) — which do NOT execute JavaScript — would
 * otherwise see the generic site-wide tags baked into index.html.
 *
 * For crawler requests to a public channel route we fetch that channel's
 * profile from the backend and rewrite the relevant <title>/<meta> tags via
 * HTMLRewriter. Human visitors are passed straight through to the SPA, whose
 * `useDocumentTitle` hook handles the in-browser title.
 */

interface Env {
  API_BACKEND: string
}

const SITE = 'Niibot'
const ORIGIN = 'https://niibot.llazypilot.com'
const DEFAULT_IMAGE = `${ORIGIN}/images/Avatar.png`

// First path segment values that are real app routes, never usernames.
const RESERVED = new Set([
  'admin',
  'dashboard',
  'settings',
  'analytics',
  'commands',
  'events',
  'timers',
  'modules',
  'discord',
  'docs',
  'activate',
  'login',
  'donate',
  'terms',
  'privacy',
  'dev',
  'api',
  'health',
  'status',
])

const CRAWLER_RE =
  /(bot|crawler|spider|facebookexternalhit|facebot|whatsapp|telegram|discord|slack|line|embedly|pinterest|preview|skype|vkshare|quora|google-inspectiontool)/i

type Target =
  | { kind: 'donate'; username: string }
  | { kind: 'commands'; username: string }
  | { kind: 'crosshairs'; username: string }

function matchTarget(pathname: string): Target | null {
  const segments = pathname.replace(/^\/+|\/+$/g, '').split('/')

  // /donate/{username}
  if (segments.length === 2 && segments[0] === 'donate') {
    return { kind: 'donate', username: segments[1] }
  }

  // /{username}/commands  and  /{username}/crosshairs
  if (segments.length === 2 && !RESERVED.has(segments[0])) {
    if (segments[1] === 'commands') return { kind: 'commands', username: segments[0] }
    if (segments[1] === 'crosshairs') return { kind: 'crosshairs', username: segments[0] }
  }

  return null
}

interface ChannelMeta {
  title: string
  description: string
  image: string
}

async function fetchMeta(
  target: Target,
  backend: string,
  username: string
): Promise<ChannelMeta | null> {
  const safe = encodeURIComponent(username)
  try {
    if (target.kind === 'donate') {
      const res = await fetch(`${backend}/api/donate/public/${safe}`, {
        signal: AbortSignal.timeout(5000),
      })
      if (!res.ok) return null
      const data = (await res.json()) as { display_name: string | null; username: string }
      const name = data.display_name || data.username || username
      return {
        title: `贊助 ${name} | ${SITE}`,
        description: `透過 Niibot 支持 ${name} 的直播。`,
        image: DEFAULT_IMAGE,
      }
    }

    const path = target.kind === 'commands' ? 'commands' : 'crosshairs'
    const res = await fetch(`${backend}/api/${path}/public/${safe}`, {
      signal: AbortSignal.timeout(5000),
    })
    if (!res.ok) return null
    const data = (await res.json()) as {
      channel?: { display_name: string | null; profile_image_url: string | null }
    }
    const name = data.channel?.display_name || username
    const image = data.channel?.profile_image_url || DEFAULT_IMAGE
    if (target.kind === 'commands') {
      return {
        title: `${name} 的指令 | ${SITE}`,
        description: `查看 ${name} 的 Twitch 頻道聊天室指令。`,
        image,
      }
    }
    return {
      title: `${name} 的準心 | ${SITE}`,
      description: `查看並複製 ${name} 的遊戲準心設定。`,
      image,
    }
  } catch {
    return null
  }
}

type Handler = HTMLRewriterElementContentHandlers

const setContent = (value: string): Handler => ({
  element: (el: Element) => {
    el.setInnerContent(value)
  },
})

const setAttr = (attr: string, value: string): Handler => ({
  element: (el: Element) => {
    el.setAttribute(attr, value)
  },
})

// The static index.html declares fixed image dimensions/type for the default
// 1080×1080 avatar. A channel's profile image has different dimensions, so we
// drop the now-inaccurate hints and let the crawler infer them.
const removeEl = (): Handler => ({
  element: (el: Element) => {
    el.remove()
  },
})

export const onRequest: PagesFunction<Env> = async context => {
  const { request } = context

  if (request.method !== 'GET') return context.next()

  const url = new URL(request.url)
  const target = matchTarget(url.pathname)
  if (!target) return context.next()

  const ua = request.headers.get('user-agent') || ''
  if (!CRAWLER_RE.test(ua)) return context.next()

  // Serve the SPA shell, then rewrite its head for the crawler.
  const response = await context.next()
  const contentType = response.headers.get('content-type') || ''
  if (!contentType.includes('text/html')) return response

  const backend = context.env.API_BACKEND
  const meta = backend ? await fetchMeta(target, backend, target.username) : null
  if (!meta) return response

  const canonical = `${ORIGIN}${url.pathname}`

  return new HTMLRewriter()
    .on('title', setContent(meta.title))
    .on('meta[name="description"]', setAttr('content', meta.description))
    .on('link[rel="canonical"]', setAttr('href', canonical))
    .on('meta[property="og:title"]', setAttr('content', meta.title))
    .on('meta[property="og:description"]', setAttr('content', meta.description))
    .on('meta[property="og:url"]', setAttr('content', canonical))
    .on('meta[property="og:image"]', setAttr('content', meta.image))
    .on('meta[property="og:image:width"]', removeEl())
    .on('meta[property="og:image:height"]', removeEl())
    .on('meta[property="og:image:type"]', removeEl())
    .on('meta[name="twitter:title"]', setAttr('content', meta.title))
    .on('meta[name="twitter:description"]', setAttr('content', meta.description))
    .on('meta[name="twitter:url"]', setAttr('content', canonical))
    .on('meta[name="twitter:image"]', setAttr('content', meta.image))
    .transform(response)
}
