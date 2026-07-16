import { describe, expect, it } from 'vitest'

import type { ChannelInsights, ViewerSummary } from '@/api/analytics'
import { deriveSuggestions, type SessionTiers } from '@/lib/insights-suggestions'

const NOW = new Date('2026-07-16T00:00:00Z').getTime()

const EMPTY_INSIGHTS: ChannelInsights = {
  total_sessions: 0,
  total_stream_seconds: 0,
  total_messages: 0,
  total_commands: 0,
  total_follows: 0,
  total_organic_subs: 0,
  total_gift_subs: 0,
  total_raids: 0,
  total_cheers: 0,
  total_bits: 0,
  top_chatters: [],
  top_commands: [],
  session_chart: [],
  top_games: [],
  loyalty_tiers: { core: 0, regular: 0, newcomer: 0 },
}

const EMPTY_TIERS: SessionTiers = { core: 0, regular: 0, newcomer: 0, silent: 0 }

function viewer(overrides: Partial<ViewerSummary>): ViewerSummary {
  return {
    user_id: '1',
    username: 'viewer',
    display_name: null,
    total_messages: 0,
    sessions_attended: 0,
    last_seen: null,
    watch_seconds: 0,
    total_bits: 0,
    total_gifts: 0,
    engagement_score: 0,
    is_subscribed: false,
    sub_tier: null,
    is_mod: false,
    is_vip: false,
    follow_since: null,
    ...overrides,
  }
}

function daysAgoIso(days: number): string {
  return new Date(NOW - days * 24 * 60 * 60 * 1000).toISOString()
}

describe('deriveSuggestions', () => {
  it('returns nothing when there are no viewers', () => {
    expect(
      deriveSuggestions(
        { insights: EMPTY_INSIGHTS, tiers: EMPTY_TIERS, viewers: [], periodDays: 30 },
        NOW
      )
    ).toEqual([])
  })

  it('flags churn risk when regulars have gone stale', () => {
    const viewers = [
      viewer({ user_id: 'a', sessions_attended: 10, last_seen: daysAgoIso(20) }),
      viewer({ user_id: 'b', sessions_attended: 10, last_seen: daysAgoIso(1) }),
    ]
    const tiers: SessionTiers = { core: 1, regular: 1, newcomer: 0, silent: 0, median: 5 }
    const result = deriveSuggestions(
      { insights: EMPTY_INSIGHTS, tiers, viewers, periodDays: 30 },
      NOW
    )
    expect(result.find(s => s.id === 'churn-risk')).toBeTruthy()
    expect(result.find(s => s.id === 'churn-risk')?.text).toContain('1 位常客')
  })

  it('flags low subscription conversion relative to follows', () => {
    const insights: ChannelInsights = {
      ...EMPTY_INSIGHTS,
      total_follows: 20,
      total_organic_subs: 1,
    }
    const viewers = [viewer({})]
    const result = deriveSuggestions({ insights, tiers: EMPTY_TIERS, viewers, periodDays: 30 }, NOW)
    expect(result.find(s => s.id === 'sub-conversion')).toBeTruthy()
  })

  it('does not flag conversion when follows are too few to judge', () => {
    const insights: ChannelInsights = { ...EMPTY_INSIGHTS, total_follows: 2, total_organic_subs: 0 }
    const viewers = [viewer({})]
    const result = deriveSuggestions({ insights, tiers: EMPTY_TIERS, viewers, periodDays: 30 }, NOW)
    expect(result.find(s => s.id === 'sub-conversion')).toBeUndefined()
  })

  it('flags a high share of silent viewers once the sample is large enough', () => {
    const viewers = Array.from({ length: 10 }, (_, i) => viewer({ user_id: String(i) }))
    const tiers: SessionTiers = { core: 1, regular: 1, newcomer: 3, silent: 5 }
    const result = deriveSuggestions(
      { insights: EMPTY_INSIGHTS, tiers, viewers, periodDays: 30 },
      NOW
    )
    expect(result.find(s => s.id === 'silent-viewers')).toBeTruthy()
  })

  it('suppresses the silent-viewer rule below the minimum sample size', () => {
    const viewers = [viewer({ user_id: 'a' }), viewer({ user_id: 'b' })]
    const tiers: SessionTiers = { core: 0, regular: 0, newcomer: 0, silent: 2 }
    const result = deriveSuggestions(
      { insights: EMPTY_INSIGHTS, tiers, viewers, periodDays: 30 },
      NOW
    )
    expect(result.find(s => s.id === 'silent-viewers')).toBeUndefined()
  })

  it('suggests thanking the top bits/gift giver when there is giving activity', () => {
    const insights: ChannelInsights = { ...EMPTY_INSIGHTS, total_bits: 500 }
    const viewers = [
      viewer({ user_id: 'a', display_name: 'Alice', total_bits: 500 }),
      viewer({ user_id: 'b', display_name: 'Bob', total_bits: 0 }),
    ]
    const result = deriveSuggestions({ insights, tiers: EMPTY_TIERS, viewers, periodDays: 30 }, NOW)
    const thanks = result.find(s => s.id === 'thank-giver')
    expect(thanks?.text).toContain('Alice')
  })

  it('falls back to a positive note when nothing else fires and core viewers are healthy', () => {
    const viewers = [viewer({ user_id: 'a', sessions_attended: 20, last_seen: daysAgoIso(0) })]
    const tiers: SessionTiers = { core: 5, regular: 0, newcomer: 0, silent: 0, median: 0 }
    const result = deriveSuggestions(
      { insights: EMPTY_INSIGHTS, tiers, viewers, periodDays: 30 },
      NOW
    )
    expect(result).toEqual([expect.objectContaining({ id: 'core-stable', tone: 'positive' })])
  })

  it('caps results at 3 and orders warning before action before positive', () => {
    const viewers = [
      ...Array.from({ length: 10 }, (_, i) =>
        viewer({ user_id: `s${i}`, sessions_attended: 10, last_seen: daysAgoIso(20) })
      ),
    ]
    const insights: ChannelInsights = {
      ...EMPTY_INSIGHTS,
      total_follows: 20,
      total_organic_subs: 1,
      total_bits: 100,
    }
    viewers[0] = viewer({ user_id: 's0', display_name: 'Top', total_bits: 100 })
    const tiers: SessionTiers = { core: 5, regular: 5, newcomer: 0, silent: 6, median: 5 }
    const result = deriveSuggestions({ insights, tiers, viewers, periodDays: 30 }, NOW)
    expect(result.length).toBeLessThanOrEqual(3)
    expect(result[0].tone).toBe('warning')
    for (let i = 1; i < result.length; i++) {
      const prevPriority = { warning: 0, action: 1, positive: 2 }[result[i - 1].tone]
      const currPriority = { warning: 0, action: 1, positive: 2 }[result[i].tone]
      expect(currPriority).toBeGreaterThanOrEqual(prevPriority)
    }
  })
})
