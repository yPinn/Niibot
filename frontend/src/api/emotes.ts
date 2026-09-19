import { apiCache, CACHE_KEYS } from '@/lib/apiCache'

import { API_ENDPOINTS, apiFetch } from './config'
import { parseApiError } from './errors'

export interface EmoteItem {
  id: string
  name: string
  url: string
  emote_type: string
  tier: string
  available: boolean
  animated: boolean
}

/** Emotes the bot account has unlocked on a DIFFERENT channel (e.g. a
 * subscription emote — usable in any chat once unlocked, not just where it
 * was earned). Not limited to channels Niibot itself monitors. */
export interface OtherChannelEmotes {
  channel_id: string
  channel_name: string
  display_name: string
  avatar: string
  emotes: EmoteItem[]
}

export interface ChannelEmotesResponse {
  bot_user_id: string
  bot_token_available: boolean
  emotes: EmoteItem[]
  other_channels: OtherChannelEmotes[]
}

async function fetchChannelEmotes(): Promise<ChannelEmotesResponse> {
  const response = await apiFetch(API_ENDPOINTS.channels.emotes, {
    credentials: 'include',
  })
  if (!response.ok) throw await parseApiError(response, '載入表情符號失敗')
  return (await response.json()) as ChannelEmotesResponse
}

// Same per-channel caching convention as STATS_CHANNEL/ANALYTICS_SUMMARY —
// the cache key is not channel-scoped, matching how those already behave
// across a tenant switch (a known, accepted gap, not introduced here).
export async function getChannelEmotes(options?: {
  forceRefresh?: boolean
}): Promise<ChannelEmotesResponse> {
  return apiCache.fetch(CACHE_KEYS.CHANNEL_EMOTES, fetchChannelEmotes, {
    ttl: 5 * 60 * 1000,
    forceRefresh: options?.forceRefresh,
  })
}
