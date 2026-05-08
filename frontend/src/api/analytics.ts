import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'

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
      if (!response.ok) throw new Error(`Failed to fetch analytics summary: ${response.statusText}`)
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
      if (!response.ok) throw new Error(`Failed to fetch top commands: ${response.statusText}`)
      return response.json() as Promise<AnalyticsCommandStat[]>
    },
    { ttl: ANALYTICS_TTL }
  )
}

export async function getSessionCommands(session_id: number): Promise<AnalyticsCommandStat[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_SESSION_COMMANDS(session_id),
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.sessionCommands(session_id), {
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`Failed to fetch session commands: ${response.statusText}`)
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
}

export async function getInsights(days: number = 30): Promise<ChannelInsights> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_INSIGHTS(days),
    async () => {
      const response = await apiFetch(`${API_ENDPOINTS.analytics.insights}?days=${days}`, {
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`Failed to fetch insights: ${response.statusText}`)
      return response.json() as Promise<ChannelInsights>
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
      if (!response.ok) throw new Error(`Failed to fetch viewers: ${response.statusText}`)
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
      if (!response.ok) throw new Error(`Failed to fetch viewer profile: ${response.statusText}`)
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
      if (!response.ok) throw new Error(`Failed to fetch channel badges: ${response.statusText}`)
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
      if (!response.ok) throw new Error(`Failed to fetch global badges: ${response.statusText}`)
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
}

export async function syncChannelRoles(): Promise<RoleSyncResult> {
  const response = await apiFetch(API_ENDPOINTS.analytics.syncRoles, {
    method: 'POST',
    credentials: 'include',
  })
  if (!response.ok) throw new Error(`Role sync failed: ${response.statusText}`)
  return response.json() as Promise<RoleSyncResult>
}

export async function getSessionEvents(session_id: number): Promise<StreamEvent[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_SESSION_EVENTS(session_id),
    async () => {
      const response = await apiFetch(API_ENDPOINTS.analytics.sessionEvents(session_id), {
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`Failed to fetch session events: ${response.statusText}`)
      return response.json() as Promise<StreamEvent[]>
    },
    { ttl: SESSION_TTL }
  )
}
