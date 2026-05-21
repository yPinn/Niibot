import { useCallback, useEffect, useRef, useState } from 'react'

import {
  getMatcherSummaries,
  getPotentialViewers,
  type MatcherChannelSummary,
  type MatcherViewersResponse,
  refreshMatcher,
} from '@/api/analytics'
import { PageMain } from '@/components/PageMain'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Badge,
  Icon,
  Skeleton,
  SlideUp,
  SlideUpSm,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { apiCache } from '@/lib/apiCache'
import { cn } from '@/lib/utils'

import { ChannelCard } from './matcher/ChannelCard'
import { ViewerTable } from './matcher/ViewerTable'

const PERIODS = [
  { label: '7 天', value: '7' },
  { label: '30 天', value: '30' },
  { label: '90 天', value: '90' },
]

function invalidateMatcherCache(days: number) {
  apiCache.delete(`matcher:summaries:${days}`)
}

function invalidateViewerCache(channelId: string) {
  apiCache.delete(`matcher:viewers:${channelId}:50:0`)
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

  const fetchViewers = useCallback(async (channelId: string) => {
    setViewerLoading(true)
    try {
      setViewerData(await getPotentialViewers(channelId))
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
    void fetchViewers(selectedChannelId)
  }, [selectedChannelId, fetchViewers])

  const handlePeriodChange = useCallback(
    (value: string) => {
      if (value === period) return
      loadedForRef.current = null
      setSelectedChannelId(null)
      setViewerData(null)
      setPeriod(value)
    },
    [period]
  )

  const handleRefresh = useCallback(async () => {
    if (isRefreshing) return
    setIsRefreshing(true)
    try {
      await refreshMatcher()
      invalidateMatcherCache(Number(period))
      if (selectedChannelId) invalidateViewerCache(selectedChannelId)
      loadedForRef.current = null
      await fetchSummaries(Number(period))
      if (selectedChannelId) await fetchViewers(selectedChannelId)
    } catch {
      // silent — button returns to idle state
    } finally {
      setIsRefreshing(false)
    }
  }, [isRefreshing, period, selectedChannelId, fetchSummaries, fetchViewers])

  const selectedChannel = summaries.find(s => s.channel_id === selectedChannelId) ?? null

  return (
    <PageMain>
      <SlideUpSm inView className="flex items-end justify-between gap-element shrink-0">
        <div>
          <h1 className="text-page-title font-bold">Matcher</h1>
          <p className="text-sub text-muted-foreground mt-0.5">
            探索各頻道觀眾重疊度，找出潛在可觸及的觀眾
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center justify-center size-10 rounded-md border bg-background text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <Icon
              icon={isRefreshing ? 'fa-solid fa-spinner' : 'fa-solid fa-rotate'}
              className={cn('text-sm', isRefreshing && 'animate-spin')}
            />
          </button>
          <Tabs value={period} onValueChange={handlePeriodChange}>
            <TabsList>
              {PERIODS.map(p => (
                <TabsTrigger key={p.value} value={p.value}>
                  {p.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      </SlideUpSm>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 md:grid-cols-3 gap-section flex-1 min-h-0 overflow-y-auto md:overflow-hidden md:grid-rows-1"
      >
        <div className="rounded-lg border bg-card p-section flex flex-col gap-2 md:overflow-y-auto">
          {summariesLoading ? (
            Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full rounded-lg" />
            ))
          ) : summaries.length === 0 ? (
            <p className="text-sub text-muted-foreground text-center py-8">尚無頻道資料</p>
          ) : (
            summaries.map(channel => (
              <ChannelCard
                key={channel.channel_id}
                channel={channel}
                isSelected={selectedChannelId === channel.channel_id}
                onClick={() => setSelectedChannelId(channel.channel_id)}
              />
            ))
          )}
        </div>

        <div className="md:col-span-2 rounded-lg border bg-card p-section flex flex-col gap-section min-h-0 md:overflow-y-auto">
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
                  <AvatarFallback className="text-sm">
                    {(selectedChannel.display_name ?? selectedChannel.channel_id)
                      .slice(0, 2)
                      .toUpperCase()}
                  </AvatarFallback>
                </Avatar>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-content font-semibold text-lg">
                      {selectedChannel.display_name ?? selectedChannel.channel_id}
                    </span>
                    {selectedChannel.is_live && (
                      <div className="flex items-center gap-1.5">
                        <span className="size-2 rounded-full bg-red-500 shrink-0" />
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
                </div>
              </div>

              <div className="flex items-center gap-3 flex-wrap shrink-0">
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2 min-w-24">
                  <span className="text-lg font-bold tabular-nums">
                    {selectedChannel.shared_chatters.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">共同觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2 min-w-24">
                  <span className="text-lg font-bold tabular-nums">
                    {selectedChannel.exclusive_to_partner.toLocaleString()}
                  </span>
                  <span className="text-label text-muted-foreground">潛在觀眾</span>
                </div>
                <div className="flex flex-col items-center rounded-lg border bg-muted/20 px-4 py-2 min-w-24">
                  <span
                    className={cn(
                      'text-lg font-bold tabular-nums',
                      selectedChannel.overlap_pct >= 30
                        ? 'text-green-500'
                        : selectedChannel.overlap_pct >= 10
                          ? 'text-blue-500'
                          : 'text-muted-foreground'
                    )}
                  >
                    {selectedChannel.overlap_pct.toFixed(1)}%
                  </span>
                  <span className="text-label text-muted-foreground">重疊率</span>
                </div>
                <Badge variant="outline" className="text-label">
                  共 {selectedChannel.monitored_chatters.toLocaleString()} 位監測觀眾
                </Badge>
              </div>

              <div className="flex-1 min-h-0">
                <ViewerTable data={viewerData} isLoading={viewerLoading} />
              </div>
            </>
          )}
        </div>
      </SlideUp>
    </PageMain>
  )
}
