export type { MatcherChannelSummary, RefreshResult, SelfStats } from '@/api/analytics'

export type CompatibilityTier = '高' | '中' | '低'

export const TIER_COLOR: Record<CompatibilityTier, string> = {
  高: 'text-status-online border-status-online/40',
  中: 'text-status-info border-status-info/40',
  低: 'text-muted-foreground',
}
