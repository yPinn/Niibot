import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'motion/react'

import {
  type ChannelBadges,
  type ChannelInsights,
  getChannelBadges,
  getInsights,
  getPlusProgramEstimate,
  listViewers,
  type PlusProgramEstimate,
  syncChannelRoles,
  type ViewerSummary,
} from '@/api/analytics'

const CHART_BOX = 'aspect-[3/2] min-h-[360px] max-h-[480px]'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import {
  AnimatePresence,
  EmptyState,
  FadeIn,
  Icon,
  SlideUp,
  Stagger,
  StaggerItem,
} from '@/components/primitives'
import {
  Input,
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
import { formatDuration } from '@/lib/format'
import { deriveSuggestions } from '@/lib/insights-suggestions'
import { cn } from '@/lib/utils'

import { LoyaltyDonut } from './insights/LoyaltyDonut'
import { PlusProgramCard } from './insights/PlusProgramCard'
import { SuggestedActions } from './insights/SuggestedActions'
import { SummaryTile } from './insights/SummaryTile'
import { SORT_COLS, type SortKey } from './insights/types'
import { ViewerList } from './insights/ViewerList'
import { ViewerScatterChart } from './insights/ViewerScatterChart'
import { ViewerSheet } from './insights/ViewerSheet'

const PERIODS = [
  { label: '7 天', value: '7' },
  { label: '30 天', value: '30' },
  { label: '90 天', value: '90' },
]

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

export default function Insights() {
  useDocumentTitle('Insights')
  const { user, isInitialized, isAffiliate } = useAuth()

  const [period, setPeriod] = useState('30')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<SortKey>('score')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
  const [initialized, setInitialized] = useState(false)
  const [viewersError, setViewersError] = useState(false)
  const [viewers, setViewers] = useState<ViewerSummary[]>([])
  const [insights, setInsights] = useState<ChannelInsights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(true)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const [hoveredUserId, setHoveredUserId] = useState<string | null>(null)
  const [channelBadges, setChannelBadges] = useState<ChannelBadges | null>(null)
  const [plusEstimate, setPlusEstimate] = useState<PlusProgramEstimate | null>(null)
  const [plusLoading, setPlusLoading] = useState(true)
  const [isSyncing, setIsSyncing] = useState(false)
  const [showScatter, setShowScatter] = useState(true)
  const [nowMs] = useState(() => Date.now())
  const loadedForRef = useRef<string | null>(null)

  const fetchViewers = useCallback(
    async (days: number, force = false) => {
      if (!user) return
      try {
        setViewersError(false)
        setViewers(await listViewers(days, force))
      } catch {
        setViewers([])
        setViewersError(true)
      } finally {
        setInitialized(true)
      }
    },
    [user]
  )

  const fetchInsights = useCallback(
    async (days: number) => {
      if (!user) return
      try {
        setInsights(await getInsights(days))
      } catch {
        setInsights(null)
      } finally {
        setInsightsLoading(false)
      }
    },
    [user]
  )

  useEffect(() => {
    if (!isInitialized || !user) return
    const key = `${user.id}:${period}`
    if (loadedForRef.current === key) return
    loadedForRef.current = key
    const days = Number(period)
    void Promise.all([fetchViewers(days), fetchInsights(days)])
  }, [isInitialized, user, period, fetchViewers, fetchInsights])

  useEffect(() => {
    if (!isInitialized || !user) return
    getChannelBadges()
      .then(setChannelBadges)
      .catch(() => null)
  }, [isInitialized, user])

  useEffect(() => {
    if (!isInitialized || !user || !isAffiliate) return
    getPlusProgramEstimate()
      .then(setPlusEstimate)
      .catch(() => setPlusEstimate(null))
      .finally(() => setPlusLoading(false))
  }, [isInitialized, user, isAffiliate])

  const handleSyncRoles = useCallback(async () => {
    if (isSyncing) return
    setIsSyncing(true)
    try {
      await syncChannelRoles()
      void fetchViewers(Number(period), true)
      apiCache.delete(CACHE_KEYS.ANALYTICS_PLUS_ESTIMATE)
      getPlusProgramEstimate()
        .then(setPlusEstimate)
        .catch(() => null)
    } catch {
      // silent
    } finally {
      setIsSyncing(false)
    }
  }, [isSyncing, period, fetchViewers])

  const handlePeriodChange = useCallback(
    (value: string) => {
      if (value === period) return
      loadedForRef.current = null
      setInitialized(false)
      setInsightsLoading(true)
      setViewersError(false)
      setPeriod(value)
    },
    [period]
  )

  const handleSort = useCallback(
    (key: SortKey) => {
      if (sort === key) {
        setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
      } else {
        const col = SORT_COLS.find(c => c.key === key)!
        setSort(key)
        setSortDir(col.natural as 'desc' | 'asc')
      }
    },
    [sort]
  )

  const sessionTiers = useMemo(() => {
    const empty = {
      core: 0,
      regular: 0,
      newcomer: 0,
      silent: 0,
      q3: undefined as number | undefined,
      median: undefined as number | undefined,
    }
    if (!viewers.length) return empty
    const sessions = viewers.map(v => v.sessions_attended).sort((a, b) => a - b)
    const n = sessions.length
    const q3 = sessions[Math.min(Math.floor(n * 0.75), n - 1)]
    const median = sessions[Math.min(Math.floor(n * 0.5), n - 1)]
    const newFollowerMs = Math.min(Number(period), 30) * 24 * 60 * 60 * 1000
    const cutoff = nowMs - newFollowerMs
    let core = 0,
      regular = 0,
      newcomer = 0,
      silent = 0
    for (const v of viewers) {
      if (v.sessions_attended >= q3) {
        core++
      } else if (v.sessions_attended >= median) {
        regular++
      } else {
        const followTs = v.follow_since ? new Date(v.follow_since).getTime() : 0
        if (followTs >= cutoff) newcomer++
        else silent++
      }
    }
    return { core, regular, newcomer, silent, q3, median }
  }, [viewers, period, nowMs])

  const { filtered, rankMap } = useMemo(() => {
    const sorted = [...viewers].sort((a, b) => {
      const dir = sortDir === 'desc' ? 1 : -1
      switch (sort) {
        case 'messages':
          return dir * (b.total_messages - a.total_messages)
        case 'watch':
          return dir * (b.watch_seconds - a.watch_seconds)
        case 'score':
          return dir * (b.engagement_score - a.engagement_score)
      }
    })
    const map = new Map(sorted.map((v, i) => [v.user_id, i + 1]))
    const q = search.trim().toLowerCase()
    const result = q
      ? sorted.filter(v => {
          if (q === 'mod' || q === '管理員' || q === '管理') return v.is_mod
          if (q === 'vip') return v.is_vip
          if (q === 'sub' || q === '訂閱') return v.is_subscribed
          return (
            (v.display_name ?? '').toLowerCase().includes(q) || v.username.toLowerCase().includes(q)
          )
        })
      : sorted
    return { filtered: result, rankMap: map }
  }, [viewers, search, sort, sortDir])

  const ins = insights ?? EMPTY_INSIGHTS

  const suggestions = useMemo(
    () =>
      deriveSuggestions({
        insights: ins,
        tiers: sessionTiers,
        viewers,
        periodDays: Number(period),
      }),
    [ins, sessionTiers, viewers, period]
  )

  return (
    <PageMain>
      <PageHeader
        title="Insights"
        description="觀眾互動與活躍度數據"
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
      </PageHeader>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-2 gap-section flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid-rows-1"
      >
        {/* ── Left: Chart + Summary tiles ──────────────────────────── */}
        <div className="rounded-lg border bg-card p-section flex flex-col gap-section min-h-0 lg:overflow-y-auto">
          {/* Chart header */}
          <div className="flex items-center justify-between shrink-0">
            <span className="text-sub font-semibold">
              {showScatter ? '觀眾分佈' : '觀眾忠誠度'}
            </span>
            <div className="flex rounded-md border overflow-hidden text-label">
              <button
                type="button"
                onClick={() => setShowScatter(true)}
                className={cn(
                  'px-2.5 py-0.5 transition-colors',
                  showScatter
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                )}
              >
                活躍圖
              </button>
              <button
                type="button"
                onClick={() => setShowScatter(false)}
                className={cn(
                  'px-2.5 py-0.5 border-l transition-colors',
                  !showScatter
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground hover:bg-accent'
                )}
              >
                忠誠度
              </button>
            </div>
          </div>

          <AnimatePresence mode="wait" initial={false}>
            {showScatter ? (
              <FadeIn key="scatter" className="shrink-0 **:outline-none">
                {!initialized ? (
                  <Skeleton className="aspect-[3/2] min-h-[360px] max-h-[480px] rounded-md" />
                ) : viewers.length === 0 ? (
                  <EmptyState
                    className="py-empty"
                    icon="fa-solid fa-chart-scatter"
                    title="尚無觀眾資料"
                    description="每場直播結束後會累積觀眾資料"
                  />
                ) : (
                  <div className={CHART_BOX}>
                    <ViewerScatterChart
                      viewers={viewers}
                      hoveredUserId={hoveredUserId}
                      onHover={setHoveredUserId}
                      channelBadges={channelBadges}
                    />
                  </div>
                )}
              </FadeIn>
            ) : (
              <motion.div
                key="donut"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.12 }}
                className="shrink-0 **:outline-none"
              >
                {!initialized ? (
                  <Skeleton className="aspect-[3/2] min-h-[360px] max-h-[480px] rounded-md" />
                ) : viewers.length === 0 ? (
                  <EmptyState
                    className="py-empty"
                    icon="fa-solid fa-chart-pie"
                    title="尚無觀眾資料"
                    description="每場直播結束後會累積觀眾資料"
                  />
                ) : (
                  <div className={CHART_BOX}>
                    <LoyaltyDonut tiers={sessionTiers} />
                  </div>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          <Separator />

          <AnimatePresence mode="wait">
            <Stagger
              key={insightsLoading ? 'l' : 'd'}
              exit={{ opacity: 0, transition: { duration: 0.08 } }}
              className="grid grid-cols-2 gap-1.5 shrink-0 sm:grid-cols-4"
            >
              {insightsLoading ? (
                Array.from({ length: 7 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 rounded-md" />
                ))
              ) : (
                <>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-tower-broadcast"
                      value={ins.total_sessions.toLocaleString()}
                      label="串流場數"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-hourglass-half"
                      value={
                        ins.total_stream_seconds > 0
                          ? formatDuration(ins.total_stream_seconds)
                          : '—'
                      }
                      label="累計直播"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-star"
                      iconClassName="text-primary/80"
                      value={ins.total_organic_subs.toLocaleString()}
                      label="自主訂閱"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-gift"
                      iconClassName="text-status-special/80"
                      value={ins.total_gift_subs.toLocaleString()}
                      label="贈禮訂閱"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-heart"
                      iconClassName="text-status-follow/80"
                      value={ins.total_follows.toLocaleString()}
                      label="新追隨"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-diamond-half-stroke"
                      iconClassName="text-primary/80"
                      value={ins.total_bits > 0 ? ins.total_bits.toLocaleString() : '—'}
                      label="小奇點"
                    />
                  </StaggerItem>
                  <StaggerItem>
                    <SummaryTile
                      icon="fa-solid fa-comments"
                      iconClassName="text-status-info/80"
                      value={ins.total_messages.toLocaleString()}
                      label="聊天訊息"
                    />
                  </StaggerItem>
                </>
              )}
            </Stagger>
          </AnimatePresence>

          {initialized && !insightsLoading && <SuggestedActions suggestions={suggestions} />}

          <PlusProgramCard
            estimate={plusEstimate}
            loading={plusLoading}
            refreshing={isSyncing}
            locked={!isAffiliate}
            onRefresh={handleSyncRoles}
          />
        </div>

        {/* ── Right: Viewer list ────────────────────────────────────── */}
        <div className="rounded-lg border bg-card p-section flex flex-col gap-section min-h-0">
          <div className="flex items-center gap-2 self-end shrink-0">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={handleSyncRoles}
                  disabled={isSyncing}
                  className="flex items-center justify-center size-10 rounded-md border bg-background text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  <Icon
                    icon={isSyncing ? 'fa-solid fa-spinner' : 'fa-solid fa-rotate'}
                    className={cn('text-sub', isSyncing && 'animate-spin')}
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent>從 Twitch 同步管理員、VIP、訂閱者與追隨日期</TooltipContent>
            </Tooltip>
            <Input
              placeholder="搜尋觀眾..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="h-10 w-44"
            />
          </div>

          <AnimatePresence mode="wait" initial={false}>
            {!initialized ? (
              <motion.div
                key="vl-loading"
                className="space-y-1"
                exit={{ opacity: 0, transition: { duration: 0.08 } }}
              >
                {Array.from({ length: 8 }).map((_, i) => (
                  <Skeleton key={i} className="h-14.25 w-full rounded-md" />
                ))}
              </motion.div>
            ) : (
              <motion.div
                key="vl-ready"
                className="flex-1 min-h-0 flex flex-col"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
              >
                {viewersError ? (
                  <EmptyState
                    className="py-empty"
                    icon="fa-solid fa-triangle-exclamation"
                    title="載入觀眾資料失敗"
                    description="請重新整理頁面，若問題持續請檢查伺服器狀態"
                  />
                ) : viewers.length === 0 ? (
                  <EmptyState
                    className="py-empty"
                    icon="fa-solid fa-users"
                    title="尚無觀眾資料"
                    description="每場直播結束後會累積觀眾資料，歷史紀錄可在此查閱"
                  />
                ) : (
                  <ViewerList
                    filtered={filtered}
                    rankMap={rankMap}
                    sort={sort}
                    sortDir={sortDir}
                    search={search}
                    hoveredUserId={hoveredUserId}
                    channelBadges={channelBadges}
                    onSort={handleSort}
                    onSelect={id => {
                      setSelectedUserId(id)
                      setSheetOpen(true)
                    }}
                    onHover={setHoveredUserId}
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </SlideUp>

      <ViewerSheet
        key={`${selectedUserId ?? 'none'}-${period}`}
        userId={selectedUserId}
        open={sheetOpen}
        onOpenChange={open => {
          if (!open) setSheetOpen(false)
        }}
        days={Number(period)}
        channelBadges={channelBadges}
      />
    </PageMain>
  )
}
