const getBaseUrl = (): string => {
  if (import.meta.env.DEV) return ''

  const rawBase = import.meta.env.VITE_API_URL || ''
  if (!rawBase) return ''
  const withProtocol = rawBase.startsWith('http') ? rawBase : `https://${rawBase}`
  return withProtocol.replace(/\/$/, '')
}

export const API_BASE_URL = getBaseUrl()

export const BOT_USERNAME = (
  (import.meta.env.VITE_BOT_USERNAME as string | undefined) ?? 'niibot_'
).toLowerCase()

const join = (path: string) => `${API_BASE_URL}${path}`

export const API_ENDPOINTS = {
  auth: {
    twitchOAuth: join('/api/auth/twitch/oauth'),
    twitchCallback: join('/api/auth/twitch/callback'),
    user: join('/api/auth/user'),
    logout: join('/api/auth/logout'),
    activate: join('/api/auth/activate'),
    pendingCode: join('/api/auth/pending-code'),
    activationRequest: join('/api/auth/activation-request'),
  },
  user: {
    preferences: join('/api/user/preferences'),
  },
  tenants: {
    list: join('/api/tenants'),
    aiSettings: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/ai/settings`),
    aiSettingsReset: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/ai/settings/reset`),
    emotes: (channelId: string) => join(`/api/tenants/${encodeURIComponent(channelId)}/emotes`),
    roleplaySets: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/roleplay-sets`),
    roleplaySet: (channelId: string, setId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/roleplay-sets/${encodeURIComponent(setId)}`
      ),
    roleplayRevisions: (channelId: string, setId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/roleplay-sets/${encodeURIComponent(setId)}/revisions`
      ),
    roleplayRevisionExport: (channelId: string, setId: string, revisionId: number) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/roleplay-sets/${encodeURIComponent(setId)}/revisions/${revisionId}/export`
      ),
    roleplayImports: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/roleplay-imports`),
    roleplayActiveRevision: (channelId: string, setId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/roleplay-sets/${encodeURIComponent(setId)}/active-revision`
      ),
    activeRoleplay: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/active-roleplay`),
    botAccounts: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/bot-accounts`),
    botInvites: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/bot-accounts/invites`),
    botInviteStatus: (channelId: string, inviteId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/bot-accounts/invites/${encodeURIComponent(inviteId)}`
      ),
    reauthorizeBot: (channelId: string, botUserId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/bot-accounts/${encodeURIComponent(botUserId)}/reauthorize-invite`
      ),
    botAuthorizationCheck: (channelId: string, botUserId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/bot-accounts/${encodeURIComponent(botUserId)}/authorization-check`
      ),
    botAccount: (channelId: string, botUserId: string) =>
      join(
        `/api/tenants/${encodeURIComponent(channelId)}/bot-accounts/${encodeURIComponent(botUserId)}`
      ),
    broadcasterAuthorization: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/broadcaster-authorization`),
    broadcasterAuthorizationCheck: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/broadcaster-authorization/check`),
    twitchCapabilities: (channelId: string) =>
      join(`/api/tenants/${encodeURIComponent(channelId)}/twitch-capabilities`),
  },
  publicBotInvites: {
    get: (publicToken: string, nonce: string) =>
      join(
        `/api/public/bot-invites/${encodeURIComponent(publicToken)}?${new URLSearchParams({ nonce })}`
      ),
    decline: (publicToken: string, nonce: string) =>
      join(
        `/api/public/bot-invites/${encodeURIComponent(publicToken)}/decline?${new URLSearchParams({ nonce })}`
      ),
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
    emotes: join('/api/channels/emotes'),
  },
  analytics: {
    summary: join('/api/analytics/summary'),
    insights: join('/api/analytics/insights'),
    plusEstimate: join('/api/analytics/plus-estimate'),
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
  commandImport: {
    sources: join('/api/commands/import/sources'),
    streamelementsPreview: join('/api/commands/import/streamelements/preview'),
    nightbotOauth: join('/api/commands/import/nightbot/oauth'),
    preview: (importId: string) => join(`/api/commands/import/preview/${importId}`),
    apply: join('/api/commands/import/apply'),
  },
  events: {
    catalog: join('/api/events/catalog'),
    configs: join('/api/events/configs'),
    updateConfig: (eventType: string) => join(`/api/events/configs/${eventType}`),
    toggleConfig: (eventType: string) => join(`/api/events/configs/${eventType}/toggle`),
    twitchRewards: join('/api/events/twitch-rewards'),
    redemptions: join('/api/events/redemptions'),
    updateRedemption: (actionType: string) => join(`/api/events/redemptions/${actionType}`),
    updateFirstSettings: join('/api/events/redemptions/first/settings'),
  },
  checkin: {
    settings: join('/api/checkin/settings'),
    leaderboard: join('/api/checkin/leaderboard'),
    collections: join('/api/checkin/collections'),
    dataSummary: join('/api/checkin/data/summary'),
    dataExport: join('/api/checkin/data/export'),
    dataClear: join('/api/checkin/data/clear'),
    importColumns: join('/api/checkin/import/summary/columns'),
    importPreview: join('/api/checkin/import/summary/preview'),
    importIdentityPreview: join('/api/checkin/import/identity/preview'),
    importApply: join('/api/checkin/import/apply'),
  },
  vip: {
    state: join('/api/vip/state'),
    settings: join('/api/vip/settings'),
    initialize: join('/api/vip/initialize'),
    sync: join('/api/vip/sync'),
    rule: (rewardId: string) => join(`/api/vip/rules/${encodeURIComponent(rewardId)}`),
    rulesEnabled: join('/api/vip/rules/enabled'),
    adopt: (redemptionId: string) =>
      join(`/api/vip/reviews/${encodeURIComponent(redemptionId)}/adopt`),
    keepExternal: (redemptionId: string) =>
      join(`/api/vip/reviews/${encodeURIComponent(redemptionId)}/keep-external`),
    entitlement: (userId: string) => join(`/api/vip/entitlements/${encodeURIComponent(userId)}`),
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
    stream: (u: string) => join(`/api/video-queue/public/${u}/stream`),
    advance: (u: string) => join(`/api/video-queue/public/${u}/advance`),
    playbackStarted: (u: string, id: number) =>
      join(`/api/video-queue/public/${u}/entries/${id}/playback-started`),
    metadata: (u: string, id: number) =>
      join(`/api/video-queue/public/${u}/entries/${id}/metadata`),
    clipSource: (u: string, id: number) =>
      join(`/api/video-queue/public/${u}/entries/${id}/clip-source`),
    reelSource: (u: string, id: number) =>
      join(`/api/video-queue/public/${u}/entries/${id}/reel-source`),
    state: join('/api/video-queue/state'),
    dashboardAdvance: join('/api/video-queue/advance'),
    history: join('/api/video-queue/history'),
    rankings: join('/api/video-queue/rankings'),
    skip: join('/api/video-queue/skip'),
    clear: join('/api/video-queue/clear'),
    settings: join('/api/video-queue/settings'),
    rotateKey: join('/api/video-queue/settings/rotate-key'),
    setNext: (id: number) => join(`/api/video-queue/entries/${id}/set-next`),
    playNow: (id: number) => join(`/api/video-queue/entries/${id}/play-now`),
    removeEntry: (id: number) => join(`/api/video-queue/entries/${id}`),
    addEntry: join('/api/video-queue/entries'),
    blocklist: join('/api/video-queue/blocklist'),
    blocklistEntry: (id: number) => join(`/api/video-queue/blocklist/${id}`),
  },
  communityOverlay: {
    stream: join('/api/live-display/public/stream'),
    events: join('/api/live-display/public/events'),
    theme: join('/api/live-display/public/theme'),
    settings: join('/api/live-display/settings'),
    rotateKey: join('/api/live-display/settings/rotate-key'),
    preview: join('/api/live-display/settings/preview'),
    themeSettings: (blockType: string) =>
      join(`/api/live-display/settings/blocks/${encodeURIComponent(blockType)}/theme`),
    themeDraft: (blockType: string) =>
      join(`/api/live-display/settings/blocks/${encodeURIComponent(blockType)}/theme/draft`),
    themePublish: (blockType: string) =>
      join(`/api/live-display/settings/blocks/${encodeURIComponent(blockType)}/theme/publish`),
    themeResetDraft: (blockType: string) =>
      join(`/api/live-display/settings/blocks/${encodeURIComponent(blockType)}/theme/reset-draft`),
  },
  timers: {
    configs: join('/api/timers/configs'),
    createConfig: join('/api/timers/configs'),
    updateConfig: (name: string) => join(`/api/timers/configs/${name}`),
    toggleConfig: (name: string) => join(`/api/timers/configs/${name}/toggle`),
    deleteConfig: (name: string) => join(`/api/timers/configs/${name}`),
  },
  streamSchedule: {
    settings: join('/api/stream-schedule/settings'),
    schedules: join('/api/stream-schedule/schedules'),
    schedule: (id: number) => join(`/api/stream-schedule/schedules/${id}`),
    segments: (scheduleId: number) => join(`/api/stream-schedule/schedules/${scheduleId}/segments`),
    segment: (id: number) => join(`/api/stream-schedule/segments/${id}`),
    gamesSearch: (query: string) =>
      join(`/api/stream-schedule/games/search?${new URLSearchParams({ q: query })}`),
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
    copy: (id: string) => join(`/api/crosshairs/public/${id}/copy`),
  },
  ai: {
    settings: join('/api/ai/settings'),
    reset: join('/api/ai/settings/reset'),
    packs: join('/api/ai/packs'),
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
    moduleAiPacks: join('/api/admin/modules/ai-packs'),
    botStatus: join('/api/admin/bot-status'),
    resetSystemBot: join('/api/admin/bot-accounts/system-default/reset-invite'),
    botEmotes: join('/api/admin/bot-emotes'),
    resyncBotEmotes: (channelId?: string) =>
      join(`/api/admin/bot-emotes/resync${channelId ? `?channel_id=${channelId}` : ''}`),
    grants: (qs: string = '') => join(`/api/admin/grants${qs}`),
    revokeGrant: (grantId: number) => join(`/api/admin/grants/${grantId}`),
    onboardingFunnel: join('/api/admin/onboarding-funnel'),
    activationRequests: join('/api/admin/activation-requests'),
    approveRequest: (userId: string) => join(`/api/admin/activation-requests/${userId}/approve`),
    rejectRequest: (userId: string) => join(`/api/admin/activation-requests/${userId}/reject`),
    membershipTimeline: (userId: string) => join(`/api/admin/memberships/${userId}/timeline`),
    suspendMembership: (userId: string) => join(`/api/admin/memberships/${userId}/suspend`),
    reinstateMembership: (userId: string) => join(`/api/admin/memberships/${userId}/reinstate`),
    logContainers: join('/api/admin/logs/containers'),
    containerLogs: (name: string) => join(`/api/admin/logs/${name}`),
    dbQuery: join('/api/admin/db/query'),
    dbSchema: join('/api/admin/db/schema'),
    clientErrors: (qs: string) => join(`/api/admin/client-errors${qs}`),
    clientErrorEvents: (fingerprint: string) =>
      join(`/api/admin/client-errors/${encodeURIComponent(fingerprint)}`),
  },
  releases: {
    list: join('/api/releases'),
  },
  clientErrors: join('/api/client-errors'),
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
