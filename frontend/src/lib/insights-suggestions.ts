import type { ChannelInsights, ViewerSummary } from '@/api/analytics'

export type SuggestionTone = 'warning' | 'action' | 'positive'

export interface Suggestion {
  id: string
  tone: SuggestionTone
  icon: string
  text: string
}

export interface SessionTiers {
  core: number
  regular: number
  newcomer: number
  silent: number
  q3?: number
  median?: number
}

export interface DeriveSuggestionsInput {
  insights: ChannelInsights
  tiers: SessionTiers
  viewers: ViewerSummary[]
  periodDays: number
}

const MIN_SAMPLE = 5
const CHURN_STALE_DAYS_MIN = 7
const CHURN_STALE_DAYS_DIVISOR = 3
const MIN_FOLLOWS_FOR_CONVERSION_RULE = 5
const SUB_CONVERSION_THRESHOLD = 0.1
const SILENT_SHARE_THRESHOLD = 0.4
const CORE_POSITIVE_MIN = 3
const MAX_SUGGESTIONS = 3

const TONE_PRIORITY: Record<SuggestionTone, number> = { warning: 0, action: 1, positive: 2 }

function daysSince(iso: string | null, now: number): number | null {
  if (!iso) return null
  const ts = new Date(iso).getTime()
  if (Number.isNaN(ts)) return null
  return (now - ts) / (24 * 60 * 60 * 1000)
}

function displayName(v: ViewerSummary): string {
  return v.display_name || v.username
}

export function deriveSuggestions(
  { insights, tiers, viewers, periodDays }: DeriveSuggestionsInput,
  now: number = Date.now()
): Suggestion[] {
  if (viewers.length === 0) return []

  const suggestions: Suggestion[] = []
  const median = tiers.median ?? 0

  // 流失風險：達到中位數場次的常客，最近卻沒回來
  const staleDaysCutoff = Math.max(CHURN_STALE_DAYS_MIN, periodDays / CHURN_STALE_DAYS_DIVISOR)
  const staleRegulars = viewers.filter(v => {
    if (v.sessions_attended < median) return false
    const idleDays = daysSince(v.last_seen, now)
    return idleDays !== null && idleDays >= staleDaysCutoff
  })
  if (staleRegulars.length > 0) {
    suggestions.push({
      id: 'churn-risk',
      tone: 'warning',
      icon: 'fa-solid fa-user-clock',
      text: `${staleRegulars.length} 位常客最近沒回來，開播時 @ 一下或私訊關心一下。`,
    })
  }

  // 訂閱轉換率偏低
  if (insights.total_follows >= MIN_FOLLOWS_FOR_CONVERSION_RULE) {
    const conversion = insights.total_organic_subs / insights.total_follows
    if (conversion < SUB_CONVERSION_THRESHOLD) {
      suggestions.push({
        id: 'sub-conversion',
        tone: 'action',
        icon: 'fa-solid fa-star',
        text: `本期新追隨 ${insights.total_follows} 人，自主訂閱只有 ${insights.total_organic_subs} 人，可以用訂閱專屬指令或福利提高誘因。`,
      })
    }
  }

  // 靜默觀眾偏多
  if (viewers.length >= MIN_SAMPLE) {
    const silentShare = tiers.silent / viewers.length
    if (silentShare >= SILENT_SHARE_THRESHOLD) {
      suggestions.push({
        id: 'silent-viewers',
        tone: 'action',
        icon: 'fa-solid fa-comment-slash',
        text: `約 ${Math.round(silentShare * 100)}% 觀眾幾乎不發言，試試拋問題或發起投票帶動聊天。`,
      })
    }
  }

  // 感謝贈禮/斗內
  if (insights.total_bits > 0 || insights.total_gift_subs > 0) {
    const topGiver = [...viewers].sort(
      (a, b) => b.total_bits + b.total_gifts * 100 - (a.total_bits + a.total_gifts * 100)
    )[0]
    if (topGiver && (topGiver.total_bits > 0 || topGiver.total_gifts > 0)) {
      suggestions.push({
        id: 'thank-giver',
        tone: 'action',
        icon: 'fa-solid fa-gift',
        text: `本期有觀眾贈禮或斗內，別忘了公開感謝 ${displayName(topGiver)}。`,
      })
    }
  }

  // 沒有其他訊號時，核心觀眾穩定也值得一提
  if (suggestions.length === 0 && tiers.core >= CORE_POSITIVE_MIN) {
    suggestions.push({
      id: 'core-stable',
      tone: 'positive',
      icon: 'fa-solid fa-heart-circle-check',
      text: `核心觀眾有 ${tiers.core} 人回訪穩定，維持現有的專屬互動就好。`,
    })
  }

  return suggestions
    .sort((a, b) => TONE_PRIORITY[a.tone] - TONE_PRIORITY[b.tone])
    .slice(0, MAX_SUGGESTIONS)
}
