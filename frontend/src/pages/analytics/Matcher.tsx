import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  getMatcherSummaries,
  getPotentialViewers,
  type MatcherChannelSummary,
  type MatcherViewersResponse,
  refreshMatcher,
} from '@/api/analytics'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { EmptyState, Icon, SlideUp } from '@/components/primitives'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { WipLockOverlay } from '@/components/WipLockOverlay'
import { SHOW_WIP_LOCK } from '@/config/env'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { apiCache, CACHE_KEYS } from '@/lib/apiCache'
import { formatCompact } from '@/lib/format'
import { cn } from '@/lib/utils'

import { TopGamesChart } from './insights/TopGamesChart'
import { ChannelCard } from './matcher/ChannelCard'
import { CollabLog } from './matcher/CollabLog'
import { ViewerTable } from './matcher/ViewerTable'

function formatPeakHours(hours: number[]): string | null {
  if (!hours.length) return null
  const min = Math.min(...hours)
  const max = Math.max(...hours)
  return min === max ? `${min}:00` : `${min}:00–${max}:59`
}

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

function invalidateMatcherCache(days: number) {
  apiCache.delete(CACHE_KEYS.MATCHER_SUMMARIES(days))
}

function invalidateViewerCache(channelId: string, days: number) {
  apiCache.delete(CACHE_KEYS.MATCHER_VIEWERS(channelId, days, 50, 0))
}

export default function Matcher() {
  useDocumentTitle('Matcher')
  const { user, isInitialized } = useAuth()

  const [period, setPeriod] = useState('30')
  const [summaries, setSummaries] = useState<MatcherChannelSummary[]>([])
  const [summariesLoading, setSummariesLoading] = useState(true)
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null)
  const [viewerData, setViewerData] = useState<MatcherViewersResponse | null>(null)
  const [viewerLoading, setViewerLoading] = useState(false)
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

  const fetchViewers = useCallback(async (channelId: string, days: number) => {
    setViewerLoading(true)
    try {
      setViewerData(await getPotentialViewers(channelId, days))
    } catch {
      setViewerData(null)
    } finally {
      setViewerLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!isInitialized || !user) return
    const key = `${user.id}:${period}`
    if (loadedForRef.current === key) return
    loadedForRef.current = key
    void fetchSummaries(Number(period))
  }, [isInitialized, user, period, fetchSummaries])

  useEffect(() => {
    if (!selectedChannelId) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchViewers(selectedChannelId, Number(period))
  }, [selectedChannelId, period, fetchViewers])

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
      if (selectedChannelId) invalidateViewerCache(selectedChannelId, days)
      loadedForRef.current = null
      await fetchSummaries(days)
      if (selectedChannelId) await fetchViewers(selectedChannelId, days)
    } catch {
      // silent — button returns to idle state
    } finally {
      setIsRefreshing(false)
    }
  }, [isRefreshing, period, selectedChannelId, fetchSummaries, fetchViewers])

  const selectedChannel = summaries.find(s => s.channel_id === selectedChannelId) ?? null
  const peakHoursLabel = selectedChannel ? formatPeakHours(selectedChannel.peak_hours ?? []) : null
  const computedAtLabel = selectedChannel ? formatComputedAt(selectedChannel.computed_at) : null

  const sortedSummaries = useMemo(
    () => [...summaries].sort((a, b) => suitabilityScore(b) - suitabilityScore(a)),
    [summaries]
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

              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-card shrink-0">
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-card-title font-bold tabular-nums">
                    {selectedChannel.shared_chatters.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">共同觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-card-title font-bold tabular-nums">
                    {selectedChannel.exclusive_to_partner.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">潛在觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span
                    className={cn(
                      'text-card-title font-bold tabular-nums',
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
                  <span className="text-card-title font-bold tabular-nums">
                    {selectedChannel.monitored_chatters.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">監測觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2">
                  <span className="text-card-title font-bold tabular-nums">
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
                  {peakHoursLabel && (
                    <span className="flex items-center gap-1">
                      <Icon icon="fa-regular fa-clock" className="text-label" />
                      {peakHoursLabel}
                    </span>
                  )}
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

                {(selectedChannel.top_games_stats?.length ?? 0) > 0 && (
                  <div className="flex flex-col gap-1">
                    <span className="text-label text-muted-foreground">熱門遊戲分類</span>
                    <div className="h-28">
                      <TopGamesChart data={selectedChannel.top_games_stats ?? []} />
                    </div>
                  </div>
                )}
              </div>

              <CollabLog
                partnerChannelId={selectedChannel.channel_id}
                windowDays={Number(period)}
              />

              <div className="flex-1 min-h-0">
                <ViewerTable data={viewerData} isLoading={viewerLoading} />
              </div>
            </>
          )}
        </div>
      </SlideUp>
      {SHOW_WIP_LOCK && <WipLockOverlay />}
    </PageMain>
  )
}
