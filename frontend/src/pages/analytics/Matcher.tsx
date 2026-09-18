import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  getMatcherSummaries,
  getSelfStats,
  type MatcherChannelSummary,
  refreshMatcher,
  type SelfStats,
} from '@/api/analytics'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { EmptyState, Icon, SlideUp } from '@/components/primitives'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Separator,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { apiCache, CACHE_KEYS } from '@/lib/apiCache'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'

import { ChannelCard } from './matcher/ChannelCard'
import { CollabLog } from './matcher/CollabLog'
import { HourHeatStrip } from './matcher/HourHeatStrip'
import { type CompatibilityTier, TIER_COLOR } from './matcher/types'

function formatComputedAt(iso: string | null): string | null {
  if (!iso) return null
  const diff = Date.now() - new Date(iso).getTime()
  const hours = Math.floor(diff / 3_600_000)
  if (hours < 1) return '剛剛更新'
  if (hours < 24) return `${hours} 小時前更新`
  const days = Math.floor(hours / 24)
  return `${days} 天前更新`
}

function broadcasterBadgeDetail(type: string | null) {
  if (type === 'partner')
    return (
      <Badge
        variant="outline"
        className="text-status-loading border-status-loading/40 text-label py-0 shrink-0"
      >
        Partner
      </Badge>
    )
  if (type === 'affiliate')
    return (
      <Badge variant="outline" className="text-primary border-primary/40 text-label py-0 shrink-0">
        Affiliate
      </Badge>
    )
  return null
}

const PERIODS = [
  { label: '7 天', value: '7' },
  { label: '30 天', value: '30' },
  { label: '90 天', value: '90' },
]

function suitabilityScore(ch: MatcherChannelSummary): number {
  if (ch.monitored_chatters < 10) return 0
  const exclusive_pct = (ch.exclusive_to_partner / ch.monitored_chatters) * 100
  return ch.overlap_pct * exclusive_pct
}

/** Percentile-bucketed compatibility tier — relative to the current candidate
 * pool rather than a fixed magic-number threshold, since suitabilityScore's
 * scale shifts with each home channel's own audience size. */
function compatibilityTiers(channels: MatcherChannelSummary[]): Map<string, CompatibilityTier> {
  const sorted = [...channels].sort((a, b) => suitabilityScore(b) - suitabilityScore(a))
  const total = sorted.length
  const tiers = new Map<string, CompatibilityTier>()
  sorted.forEach((ch, index) => {
    if (suitabilityScore(ch) <= 0) {
      tiers.set(ch.channel_id, '低')
      return
    }
    const percentile = index / total
    tiers.set(ch.channel_id, percentile < 1 / 3 ? '高' : percentile < 2 / 3 ? '中' : '低')
  })
  return tiers
}

function commonGames(a: string[], b: string[]): string[] {
  const bSet = new Set(b)
  return a.filter(game => bSet.has(game))
}

function invalidateMatcherCache(days: number) {
  apiCache.delete(CACHE_KEYS.MATCHER_SUMMARIES(days))
}

function invalidateSelfStatsCache(days: number) {
  apiCache.delete(CACHE_KEYS.MATCHER_SELF_STATS(days))
}

export default function Matcher() {
  useDocumentTitle('Matcher')
  const { user, isInitialized } = useAuth()

  const [period, setPeriod] = useState('30')
  const [summaries, setSummaries] = useState<MatcherChannelSummary[]>([])
  const [summariesLoading, setSummariesLoading] = useState(true)
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null)
  const [selfStats, setSelfStats] = useState<SelfStats | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const loadedForRef = useRef<string | null>(null)

  const fetchSummaries = useCallback(
    async (days: number) => {
      if (!user) return
      setSummariesLoading(true)
      try {
        setSummaries(await getMatcherSummaries(days))
      } catch {
        setSummaries([])
      } finally {
        setSummariesLoading(false)
      }
    },
    [user]
  )

  const fetchSelfStats = useCallback(async (days: number) => {
    try {
      setSelfStats(await getSelfStats(days))
    } catch {
      setSelfStats(null)
    }
  }, [])

  useEffect(() => {
    if (!isInitialized || !user) return
    const key = `${user.id}:${period}`
    if (loadedForRef.current === key) return
    loadedForRef.current = key
    void fetchSummaries(Number(period))
    void fetchSelfStats(Number(period))
  }, [isInitialized, user, period, fetchSummaries, fetchSelfStats])

  const handlePeriodChange = useCallback((value: string) => {
    setPeriod(value)
  }, [])

  const handleRefresh = useCallback(async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    const days = Number(period)
    try {
      await refreshMatcher()
      invalidateMatcherCache(days)
      invalidateSelfStatsCache(days)
      loadedForRef.current = null
      await fetchSummaries(days)
      await fetchSelfStats(days)
    } catch {
      // silent — button returns to idle state
    } finally {
      setIsRefreshing(false)
    }
  }, [isRefreshing, period, fetchSummaries, fetchSelfStats])

  const selectedChannel = summaries.find(s => s.channel_id === selectedChannelId) ?? null
  const computedAtLabel = selectedChannel ? formatComputedAt(selectedChannel.computed_at) : null

  const sortedSummaries = useMemo(
    () => [...summaries].sort((a, b) => suitabilityScore(b) - suitabilityScore(a)),
    [summaries]
  )
  const tierByChannelId = useMemo(() => compatibilityTiers(summaries), [summaries])
  const selectedGameOverlap = useMemo(
    () =>
      selectedChannel && selfStats
        ? commonGames(selectedChannel.top_games, selfStats.top_games)
        : [],
    [selectedChannel, selfStats]
  )

  return (
    <PageMain>
      <PageHeader
        title="Matcher"
        description="探索各頻道觀眾重疊度，找出潛在可觸及的觀眾"
        className="items-end shrink-0"
      >
        <Tabs value={period} onValueChange={handlePeriodChange}>
          <TabsList>
            {PERIODS.map(p => (
              <TabsTrigger key={p.value} value={p.value}>
                {p.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Tooltip>
          <TooltipTrigger asChild>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="flex select-none items-center justify-center size-10 rounded-md border bg-background text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <Icon
                icon={isRefreshing ? 'fa-solid fa-spinner' : 'fa-solid fa-rotate'}
                className={cn('text-sub', isRefreshing && 'animate-spin')}
              />
            </button>
          </TooltipTrigger>
          <TooltipContent>重新整理資料</TooltipContent>
        </Tooltip>
      </PageHeader>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-3 gap-section flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid-rows-1"
      >
        <div className="rounded-lg border bg-card p-section flex flex-col gap-card lg:overflow-y-auto">
          {summariesLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="flex flex-col gap-2 p-3 rounded-lg border">
                <div className="flex items-center gap-2.5">
                  <Skeleton className="size-9 rounded-full shrink-0" />
                  <div className="flex items-center gap-1.5 flex-1">
                    <Skeleton className="h-4 w-24 rounded" />
                    <Skeleton className="h-4 w-14 rounded" />
                    <Skeleton className="h-4 w-8 rounded" />
                  </div>
                </div>
                <div className="flex items-center gap-1.5">
                  <Skeleton className="h-5 w-14 rounded" />
                  <Skeleton className="h-5 w-14 rounded" />
                  <Skeleton className="h-5 w-12 rounded" />
                </div>
              </div>
            ))
          ) : summaries.length === 0 ? (
            <EmptyState
              icon="fa-solid fa-tower-broadcast"
              title="尚無頻道資料"
              description="系統分析後將列出可能重疊觀眾的頻道"
            />
          ) : (
            sortedSummaries.map(channel => (
              <ChannelCard
                key={channel.channel_id}
                channel={channel}
                tier={tierByChannelId.get(channel.channel_id) ?? '低'}
                isSelected={selectedChannelId === channel.channel_id}
                onClick={() => setSelectedChannelId(channel.channel_id)}
              />
            ))
          )}
        </div>

        <div className="lg:col-span-2 rounded-lg border bg-card p-section flex flex-col gap-section min-h-0 lg:overflow-y-auto">
          {!selectedChannel ? (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-sub text-muted-foreground">選擇左側頻道以查看詳細分析</p>
            </div>
          ) : (
            <>
              <div className="flex items-start gap-3 shrink-0">
                <Avatar className="size-12 shrink-0">
                  <AvatarImage
                    src={selectedChannel.profile_image_url ?? undefined}
                    alt={selectedChannel.display_name ?? selectedChannel.channel_id}
                  />
                  <AvatarFallback className="text-sub">
                    {(selectedChannel.display_name ?? selectedChannel.channel_id)
                      .slice(0, 2)
                      .toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-card-title font-semibold">
                      {selectedChannel.display_name ?? selectedChannel.channel_id}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn(
                        'text-label py-0 shrink-0',
                        TIER_COLOR[tierByChannelId.get(selectedChannel.channel_id) ?? '低']
                      )}
                    >
                      契合度 {tierByChannelId.get(selectedChannel.channel_id) ?? '低'}
                    </Badge>
                    {broadcasterBadgeDetail(selectedChannel.broadcaster_type)}
                    {selectedChannel.language && (
                      <Badge
                        variant="outline"
                        className="text-label py-0 font-mono uppercase text-muted-foreground shrink-0"
                      >
                        {selectedChannel.language}
                      </Badge>
                    )}
                    {selectedChannel.is_live && (
                      <div className="flex items-center gap-1.5">
                        <span className="size-2 rounded-full bg-status-live shrink-0" />
                        <span className="text-label text-muted-foreground">
                          {selectedChannel.viewer_count.toLocaleString()} 人觀看
                        </span>
                      </div>
                    )}
                  </div>
                  {selectedChannel.is_live && selectedChannel.stream_title && (
                    <p className="text-label text-muted-foreground truncate mt-0.5">
                      {selectedChannel.stream_game && (
                        <span className="mr-1">[{selectedChannel.stream_game}]</span>
                      )}
                      {selectedChannel.stream_title}
                    </p>
                  )}
                  {selectedChannel.description && (
                    <p className="text-label text-muted-foreground line-clamp-2 mt-1">
                      {selectedChannel.description}
                    </p>
                  )}
                </div>
              </div>

              <CollabLog
                partnerChannelId={selectedChannel.channel_id}
                windowDays={Number(period)}
              />

              <Separator />

              {/* 重疊率／尚未重疊 are the two numbers this whole tool exists to
                  surface — sized up so they read as the point, not tied with
                  the three supporting counts around them. */}
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-card shrink-0">
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-content font-semibold tabular-nums">
                    {selectedChannel.shared_chatters.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">共同觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-page-title font-bold text-primary tabular-nums">
                    {selectedChannel.exclusive_to_partner.toLocaleString()}
                  </span>
                  <Tooltip>
                    <TooltipTrigger asChild>
                      <span className="text-label text-muted-foreground inline-flex items-center gap-0.5 cursor-help">
                        尚未重疊
                        <Icon icon="fa-regular fa-circle-question" className="text-label" />
                      </span>
                    </TooltipTrigger>
                    <TooltipContent className="max-w-56">
                      僅統計聊天室出席紀錄的帳號，不含純觀看不進聊天室的觀眾，也不代表對方完全不認識你。
                    </TooltipContent>
                  </Tooltip>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span
                    className={cn(
                      'text-page-title font-bold tabular-nums',
                      selectedChannel.overlap_pct >= 30
                        ? 'text-status-online'
                        : selectedChannel.overlap_pct >= 10
                          ? 'text-status-info'
                          : 'text-muted-foreground'
                    )}
                  >
                    {selectedChannel.overlap_pct.toFixed(1)}%
                  </span>
                  <span className="text-label text-muted-foreground">重疊率</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-content font-semibold tabular-nums">
                    {selectedChannel.monitored_chatters.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">監測觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-content font-semibold tabular-nums">
                    {selectedChannel.channel_view_count != null
                      ? formatCompact(selectedChannel.channel_view_count)
                      : '—'}
                  </span>
                  <span className="text-label text-muted-foreground">累積觀看</span>
                </div>
              </div>

              <div className="flex flex-col gap-2 shrink-0">
                {(selectedChannel.tags?.length ?? 0) > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {selectedChannel.tags.map(tag => (
                      <Badge
                        key={tag}
                        variant="outline"
                        className="text-label py-0 px-1.5 text-muted-foreground border-border/60"
                      >
                        {tag}
                      </Badge>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-section text-label text-muted-foreground flex-wrap">
                  {selectedChannel.session_count > 0 && (
                    <span className="flex items-center gap-1">
                      <Icon icon="fa-solid fa-video" className="text-label" />
                      {selectedChannel.session_count} 場次
                      {selectedChannel.avg_stream_hours > 0 &&
                        ` · 均 ${selectedChannel.avg_stream_hours}h`}
                    </span>
                  )}
                  {computedAtLabel && (
                    <span className="flex items-center gap-1 ml-auto shrink-0">
                      <Icon icon="fa-regular fa-circle-check" className="text-label" />
                      {computedAtLabel}
                    </span>
                  )}
                </div>
              </div>

              <Separator />

              <div className="flex flex-col gap-card shrink-0">
                <span className="text-label text-muted-foreground">共同點</span>

                {selectedGameOverlap.length > 0 ? (
                  <div className="flex flex-col gap-1">
                    <span className="text-label text-muted-foreground/70">共同遊戲分類</span>
                    <div className="flex items-center gap-1.5 flex-wrap">
                      {selectedGameOverlap.map(game => (
                        <Badge
                          key={game}
                          variant="outline"
                          className="text-label py-0 px-1.5 text-status-online border-status-online/40"
                        >
                          {game}
                        </Badge>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-label text-muted-foreground/70">目前沒有相同的熱門遊戲分類</p>
                )}

                <div className="flex flex-col gap-1">
                  <span className="text-label text-muted-foreground/70">開台時段重疊</span>
                  <HourHeatStrip
                    homeHistogram={selfStats?.hour_histogram ?? []}
                    partnerHistogram={selectedChannel.hour_histogram}
                    partnerLabel={selectedChannel.display_name ?? selectedChannel.channel_id}
                  />
                </div>
              </div>
            </>
          )}
        </div>
      </SlideUp>
    </PageMain>
  )
}
