import { API_ENDPOINTS } from './config'

export interface SessionSummary {
  session_id: number
  channel_id: string
  started_at: string
  ended_at: string | null
  title: string | null
  game_name: string | null
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

export async function getAnalyticsSummary(days: number = 30): Promise<AnalyticsSummary> {
  const response = await fetch(`${API_ENDPOINTS.analytics.summary}?days=${days}`, {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch analytics summary: ${response.statusText}`)
  }

  return response.json()
}

export async function getTopCommands(
  days: number = 30,
  limit: number = 10
): Promise<AnalyticsCommandStat[]> {
  const response = await fetch(
    `${API_ENDPOINTS.analytics.topCommands}?days=${days}&limit=${limit}`,
    {
      credentials: 'include',
    }
  )

  if (!response.ok) {
    throw new Error(`Failed to fetch top commands: ${response.statusText}`)
  }

  return response.json()
}

export async function getSessionCommands(sessionId: number): Promise<AnalyticsCommandStat[]> {
  const response = await fetch(API_ENDPOINTS.analytics.sessionCommands(sessionId), {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch session commands: ${response.statusText}`)
  }

  return response.json()
}

export async function getSessionEvents(sessionId: number): Promise<StreamEvent[]> {
  const response = await fetch(API_ENDPOINTS.analytics.sessionEvents(sessionId), {
    credentials: 'include',
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch session events: ${response.statusText}`)
  }

  return response.json()
}
