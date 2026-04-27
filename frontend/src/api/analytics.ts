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
  total_messages: number
  total_commands: number
  total_follows: number
  total_subs: number
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
    { ttl: 5 * 60 * 1000 }
  )
}

export interface ViewerSummary {
  user_id: string
  username: string
  display_name: string | null
  total_messages: number
  sessions_attended: number
  last_seen: string | null
  total_bits: number
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
}

export interface ViewerProfile extends ViewerSummary {
  profile_image_url: string | null
  follow_since: string | null
  twitch: ViewerTwitchStatus | null
  events: ViewerEvent[]
}

export async function listViewers(days: number = 30): Promise<ViewerSummary[]> {
  return apiCache.fetch(
    CACHE_KEYS.ANALYTICS_VIEWERS(days),
    async () => {
      const response = await apiFetch(`${API_ENDPOINTS.analytics.viewers}?days=${days}`, {
        credentials: 'include',
      })
      if (!response.ok) throw new Error(`Failed to fetch viewers: ${response.statusText}`)
      return response.json() as Promise<ViewerSummary[]>
    },
    { ttl: 5 * 60 * 1000 }
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
    { ttl: 5 * 60 * 1000 }
  )
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
