import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export interface SessionSummary {
  session_id: number
  channel_id: string
  started_at: string
  ended_at: string | null
  title: string | null
  game_name: string | null
  game_id: string | null
  duration_hours: number
  total_commands: number
  new_follows: number
  new_subs: number
  raids_received: number
}

export interface AnalyticsCommandStat {
  command_name: string
  usage_count: number
  last_used_at: string
}

export interface StreamEvent {
  event_type: 'follow' | 'subscribe' | 'raid'
  user_id: string | null
  username: string | null
  display_name: string | null
  metadata: Record<string, unknown> | null
  occurred_at: string
}

export interface AnalyticsSummary {
  total_sessions: number
  total_stream_hours: number
  total_commands: number
  total_follows: number
  total_subs: number
  avg_session_duration: number
  recent_sessions: SessionSummary[]
}

const ANALYTICS_TTL = 5 * 60 * 1000
const SESSION_TTL = 10 * 60 * 1000

export async function getAnalyticsSummary(days: number = 30): Promise<AnalyticsSummary> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_SUMMARY(days),
    async () => {
      const response = await apiFetch(`${API_ENDPOINTS.analytics.summary}?days=${days}`, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入數據總覽失敗')
      return response.json() as Promise<AnalyticsSummary>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export async function getTopCommands(
  days: number = 30,
  limit: number = 10
): Promise<AnalyticsCommandStat[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_TOP_COMMANDS(days, limit),
    async () => {
      const response = await apiFetch(
        `${API_ENDPOINTS.analytics.topCommands}?days=${days}&limit=${limit}`,
        { credentials: 'include' }
      )
      if (!response.ok) throw await parseApiError(response, '載入熱門指令失敗')
      return response.json() as Promise<AnalyticsCommandStat[]>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export async function getSessionCommands(sessionId: number): Promise<AnalyticsCommandStat[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_SESSION_COMMANDS(sessionId),
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.sessionCommands(sessionId), {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入場次指令失敗')
      return response.json() as Promise<AnalyticsCommandStat[]>
    },
    { ttl: SESSION_TTL }
  )
}

export interface InsightsChatterStat {
  username: string
  display_name: string | null
  message_count: number
}

export interface InsightsCommandStat {
  command_name: string
  usage_count: number
}

export interface SessionChartPoint {
  started_at: string
  game_name: string | null
  total_watch_hours: number
}

export interface InsightsGameStat {
  game_name: string
  session_count: number
  total_hours: number
}

export interface LoyaltyTiers {
  core: number
  regular: number
  newcomer: number
}

export interface ChannelInsights {
  total_sessions: number
  total_stream_seconds: number
  total_messages: number
  total_commands: number
  total_follows: number
  total_organic_subs: number
  total_gift_subs: number
  total_raids: number
  total_cheers: number
  total_bits: number
  top_chatters: InsightsChatterStat[]
  top_commands: InsightsCommandStat[]
  session_chart: SessionChartPoint[]
  top_games: InsightsGameStat[]
  loyalty_tiers: LoyaltyTiers
}

export async function getInsights(days: number = 30): Promise<ChannelInsights> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_INSIGHTS(days),
    async () => {
      const response = await apiFetch(`${API_ENDPOINTS.analytics.insights}?days=${days}`, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入洞察數據失敗')
      return response.json() as Promise<ChannelInsights>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export interface PlusProgramEstimate {
  confirmed_points: number
  confirmed_subs: number
  pending_points: number
  pending_subs: number
  tier_breakdown: { t1: number; t2: number; t3: number }
  plan_confirmed: string
  plan_ceiling: string
  data_as_of: string | null
}

export async function getPlusProgramEstimate(): Promise<PlusProgramEstimate> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_PLUS_ESTIMATE,
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.plusEstimate, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入加強版方案積分失敗')
      return response.json() as Promise<PlusProgramEstimate>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export interface ViewerSummary {
  user_id: string
  username: string
  display_name: string | null
  total_messages: number
  sessions_attended: number
  last_seen: string | null
  watch_seconds: number
  total_bits: number
  total_gifts: number
  engagement_score: number
  is_subscribed: boolean
  sub_tier: string | null
  is_mod: boolean
  is_vip: boolean
  follow_since: string | null
}

export interface ViewerEvent {
  event_type: 'follow' | 'subscribe' | 'cheer' | string
  metadata: Record<string, unknown> | null
  occurred_at: string
}

export interface ViewerTwitchStatus {
  is_subscribed: boolean
  sub_tier: string | null
  sub_gifted: boolean | null
  sub_gifter: string | null
  is_mod: boolean
  is_vip: boolean
  is_banned: boolean
  ban_expires_at: string | null
  ban_reason: string | null
}

export interface ViewerSessionAttendance {
  session_id: number
  started_at: string
  stream_duration_seconds: number
  viewer_watch_seconds: number
  attended: boolean
}

export interface ViewerProfile extends ViewerSummary {
  profile_image_url: string | null
  offline_image_url: string | null
  account_created_at: string | null
  broadcaster_type: string | null
  follow_since: string | null
  streak_count: number
  best_streak: number
  twitch: ViewerTwitchStatus | null
  events: ViewerEvent[]
  session_attendance: ViewerSessionAttendance[]
}

export async function listViewers(
  days: number = 30,
  forceRefresh = false
): Promise<ViewerSummary[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_VIEWERS(days),
    async () => {
      const response = await apiFetch(`${API_ENDPOINTS.analytics.viewers}?days=${days}`, {
        credentials: 'include',
        ...(forceRefresh && { cache: 'no-store' as RequestCache }),
      })
      if (!response.ok) throw await parseApiError(response, '載入觀眾清單失敗')
      return response.json() as Promise<ViewerSummary[]>
    },
    { ttl: ANALYTICS_TTL, forceRefresh }
  )
}

export async function getViewerProfile(userId: string, days: number = 30): Promise<ViewerProfile> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_VIEWER_PROFILE(userId, days),
    async () => {
      const response = await apiFetch(
        `${API_ENDPOINTS.analytics.viewerProfile(userId)}?days=${days}`,
        { credentials: 'include' }
      )
      if (!response.ok) throw await parseApiError(response, '載入觀眾檔案失敗')
      return response.json() as Promise<ViewerProfile>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export interface TwitchBadgeVersion {
  id: string
  title: string
  image_url_1x: string | null
  image_url_2x: string | null
  image_url_4x: string | null
}

export interface ChannelBadges {
  /** 1x URL for backward compatibility */
  subscriber_1m: string | null
  /** 1x URL for backward compatibility */
  founder: string | null
  sets: {
    subscriber: TwitchBadgeVersion[]
    founder: TwitchBadgeVersion[]
    bits: TwitchBadgeVersion[]
  }
}

export async function getChannelBadges(): Promise<ChannelBadges> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_CHANNEL_BADGES,
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.channelBadges, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入頻道徽章失敗')
      return response.json() as Promise<ChannelBadges>
    },
    { ttl: 60 * 60 * 1000 }
  )
}

export type GlobalBadgeSets = Record<string, TwitchBadgeVersion[]>

export async function getGlobalBadges(): Promise<GlobalBadgeSets> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_GLOBAL_BADGES,
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.globalBadges, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入全域徽章失敗')
      return response.json() as Promise<GlobalBadgeSets>
    },
    { ttl: 24 * 60 * 60 * 1000 }
  )
}

export interface RoleSyncResult {
  mods_synced: number
  vips_synced: number
  subs_synced: number
  follows_synced: number
  bans_synced: number
}

export async function syncChannelRoles(): Promise<RoleSyncResult> {
  const response = await apiFetch(API_ENDPOINTS.analytics.syncRoles, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '同步身分組失敗')
  return response.json() as Promise<RoleSyncResult>
}

export interface MatcherChannelSummary {
  channel_id: string
  login: string | null
  display_name: string | null
  profile_image_url: string | null
  broadcaster_type: string | null
  description: string | null
  language: string | null
  tags: string[]
  is_live: boolean
  viewer_count: number
  stream_title: string | null
  stream_game: string | null
  stream_thumbnail_url: string | null
  monitored_chatters: number
  shared_chatters: number
  exclusive_to_partner: number
  overlap_pct: number
  computed_at: string | null
  top_games: string[]
  top_games_stats: InsightsGameStat[]
  peak_hours: number[]
  session_count: number
  avg_stream_hours: number
  channel_view_count: number | null
}

export interface PotentialViewer {
  user_id: string
  username: string
  display_name: string | null
  partner_sessions: number
  partner_messages: number
  partner_watch_sec: number
  partner_last_seen: string | null
  home_sessions: number
  home_messages: number
  potential_score: number
}

export interface MatcherViewersResponse {
  partner_channel_id: string
  total: number
  viewers: PotentialViewer[]
}

export interface RefreshResult {
  refreshed_channels: number
}

const MATCHER_TTL = 5 * 60 * 1000

export async function getMatcherSummaries(days: number = 30): Promise<MatcherChannelSummary[]> {
  return apiCache.fetch(
    CACHE_KEYS.MATCHER_SUMMARIES(days),
    async () => {
      const response = await apiFetch(`/api/analytics/matcher?days=${days}`, {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入配對數據失敗')
      return response.json() as Promise<MatcherChannelSummary[]>
    },
    { ttl: MATCHER_TTL }
  )
}

export async function getPotentialViewers(
  partnerChannelId: string,
  days: number = 30,
  limit: number = 50,
  offset: number = 0
): Promise<MatcherViewersResponse> {
  return apiCache.fetch(
    CACHE_KEYS.MATCHER_VIEWERS(partnerChannelId, days, limit, offset),
    async () => {
      const response = await apiFetch(
        `/api/analytics/matcher/${partnerChannelId}/viewers?days=${days}&limit=${limit}&offset=${offset}`,
        { credentials: 'include' }
      )
      if (!response.ok) throw await parseApiError(response, '載入潛在觀眾失敗')
      return response.json() as Promise<MatcherViewersResponse>
    },
    { ttl: MATCHER_TTL }
  )
}

export async function refreshMatcher(): Promise<RefreshResult> {
  const response = await apiFetch('/api/analytics/matcher/refresh', {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '重新整理配對失敗')
  return response.json() as Promise<RefreshResult>
}

export async function getSessionEvents(sessionId: number): Promise<StreamEvent[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_SESSION_EVENTS(sessionId),
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.sessionEvents(sessionId), {
        credentials: 'include',
      })
      if (!response.ok) throw await parseApiError(response, '載入場次事件失敗')
      return response.json() as Promise<StreamEvent[]>
    },
    { ttl: SESSION_TTL }
  )
}
