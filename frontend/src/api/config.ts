const getBaseUrl = (): string => {
  const rawBase = import.meta.env.VITE_API_URL || ''
  if (!rawBase) {
    if (import.meta.env.DEV) {
      console.warn(
        '[config] VITE_API_URL is not set — falling back to relative paths (Vite proxy).'
      )
    }
    return ''
  }
  const withProtocol = rawBase.startsWith('http') ? rawBase : `https://${rawBase}`
  return withProtocol.replace(/\/$/, '')
}

export const API_BASE_URL = getBaseUrl()

const join = (path: string) => `${API_BASE_URL}${path}`

export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: join('/api/auth/twitch/oauth'),
    twitchCallback: join('/api/auth/twitch/callback'),
    user: join('/api/auth/user'),
    logout: join('/api/auth/logout'),
    activate: join('/api/auth/activate'),
    requestActivation: join('/api/auth/request-activation'),
    activationRequest: join('/api/auth/activation-request'),
  },
  user: {
    preferences: join('/api/user/preferences'),
  },
  channels: {
    twitch: {
      monitored: join('/api/channels/twitch/monitored'),
      myStatus: join('/api/channels/twitch/my-status'),
      toggle: join('/api/channels/twitch/toggle'),
      modStatus: join('/api/channels/twitch/mod-status'),
      grantMod: join('/api/channels/twitch/grant-mod'),
    },
    defaults: join('/api/channels/defaults'),
  },
  analytics: {
    summary: join('/api/analytics/summary'),
    insights: join('/api/analytics/insights'),
    viewers: join('/api/analytics/viewers'),
    viewerProfile: (userId: string) => join(`/api/analytics/viewers/${userId}`),
    topCommands: join('/api/analytics/top-commands'),
    sessionCommands: (session_id: number) => join(`/api/analytics/sessions/${session_id}/commands`),
    sessionEvents: (session_id: number) => join(`/api/analytics/sessions/${session_id}/events`),
    channelBadges: join('/api/analytics/channel/badges'),
    globalBadges: join('/api/analytics/channel/badges/global'),
    syncRoles: join('/api/analytics/sync-roles'),
  },
  stats: {
    channel: join('/api/stats/channel'),
  },
  commands: {
    configs: join('/api/commands/configs'),
    createConfig: join('/api/commands/configs'),
    updateConfig: (commandName: string) => join(`/api/commands/configs/${commandName}`),
    toggleConfig: (commandName: string) => join(`/api/commands/configs/${commandName}/toggle`),
    deleteConfig: (commandName: string) => join(`/api/commands/configs/${commandName}`),
    public: (username: string) => join(`/api/commands/public/${username}`),
  },
  events: {
    configs: join('/api/events/configs'),
    updateConfig: (eventType: string) => join(`/api/events/configs/${eventType}`),
    toggleConfig: (eventType: string) => join(`/api/events/configs/${eventType}/toggle`),
    twitchRewards: join('/api/events/twitch-rewards'),
    redemptions: join('/api/events/redemptions'),
    updateRedemption: (actionType: string) => join(`/api/events/redemptions/${actionType}`),
  },
  gameQueue: {
    state: join('/api/game-queue/state'),
    advance: join('/api/game-queue/advance'),
    removeEntry: (id: number) => join(`/api/game-queue/entries/${id}`),
    promoteEntry: (id: number) => join(`/api/game-queue/entries/${id}/promote`),
    clear: join('/api/game-queue/clear'),
    settings: join('/api/game-queue/settings'),
    public: (username: string) => join(`/api/game-queue/public/${username}`),
  },
  videoQueue: {
    public: (u: string) => join(`/api/video-queue/public/${u}`),
    advance: (u: string) => join(`/api/video-queue/public/${u}/advance`),
    metadata: (u: string, id: number) =>
      join(`/api/video-queue/public/${u}/entries/${id}/metadata`),
    state: join('/api/video-queue/state'),
    skip: join('/api/video-queue/skip'),
    clear: join('/api/video-queue/clear'),
    settings: join('/api/video-queue/settings'),
    setNext: (id: number) => join(`/api/video-queue/entries/${id}/set-next`),
    playNow: (id: number) => join(`/api/video-queue/entries/${id}/play-now`),
    addEntry: join('/api/video-queue/entries'),
  },
  timers: {
    configs: join('/api/timers/configs'),
    createConfig: join('/api/timers/configs'),
    updateConfig: (name: string) => join(`/api/timers/configs/${name}`),
    toggleConfig: (name: string) => join(`/api/timers/configs/${name}/toggle`),
    deleteConfig: (name: string) => join(`/api/timers/configs/${name}`),
  },
  triggers: {
    configs: join('/api/triggers/configs'),
    createConfig: join('/api/triggers/configs'),
    updateConfig: (name: string) => join(`/api/triggers/configs/${name}`),
    toggleConfig: (name: string) => join(`/api/triggers/configs/${name}/toggle`),
    deleteConfig: (name: string) => join(`/api/triggers/configs/${name}`),
  },
  paymentConfigs: {
    list: join('/api/payment-configs'),
    upsert: (platform: string) => join(`/api/payment-configs/${platform}`),
    delete: (platform: string) => join(`/api/payment-configs/${platform}`),
  },
  crosshairs: {
    allPublic: join('/api/crosshairs/public'),
    public: (username: string) => join(`/api/crosshairs/public/${username}`),
    list: join('/api/crosshairs'),
    create: join('/api/crosshairs'),
    update: (id: string) => join(`/api/crosshairs/${id}`),
    delete: (id: string) => join(`/api/crosshairs/${id}`),
  },
  donate: {
    public: (username: string) => join(`/api/donate/public/${username}`),
    checkout: (username: string) => join(`/api/donate/${username}/checkout`),
  },
  bots: {
    twitch: {
      status: join('/api/bots/twitch/status'),
      health: join('/api/bots/twitch/health'),
    },
    discord: {
      status: join('/api/bots/discord/status'),
      health: join('/api/bots/discord/health'),
    },
  },
  admin: {
    channels: join('/api/admin/channels'),
    activationCodes: join('/api/admin/activation-codes'),
    activationRequests: join('/api/admin/activation-requests'),
    approveRequest: (id: number) => join(`/api/admin/activation-requests/${id}/approve`),
    rejectRequest: (id: number) => join(`/api/admin/activation-requests/${id}/reject`),
  },
  health: join('/health'),
  status: join('/status'),
} as const

// OAuth redirect guard — validates provider origin before following the URL.
const TRUSTED_OAUTH_ORIGINS: Record<string, Set<string>> = {
  twitch: new Set(['https://id.twitch.tv']),
}

export function assertTrustedOAuthUrl(raw: unknown, provider: 'twitch'): string {
  if (typeof raw !== 'string' || !raw) throw new Error('No OAuth URL returned')
  let url: URL
  try {
    url = new URL(raw)
  } catch {
    throw new Error('Malformed OAuth URL')
  }
  if (url.protocol !== 'https:' || !TRUSTED_OAUTH_ORIGINS[provider].has(url.origin)) {
    throw new Error('OAuth redirect was blocked: untrusted origin')
  }
  return raw
}

// Fetch wrapper: retries once on 503, dispatches auth events on 401/403.
export async function apiFetch(
  input: RequestInfo | URL,
  init?: RequestInit,
  retries = 1
): Promise<Response> {
  let attempt = 0
  while (true) {
    const res = await fetch(input, init)
    if (res.status === 503 && attempt < retries) {
      attempt++
      await new Promise(r => setTimeout(r, 1500))
      continue
    }
    if (res.status === 401) {
      window.dispatchEvent(new CustomEvent('auth:unauthorized'))
    }
    if (res.status === 403 && res.headers.get('X-Reauth-Required') === 'true') {
      window.dispatchEvent(new CustomEvent('auth:reauth-required'))
    }
    return res
  }
}
