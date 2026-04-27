import React, { useCallback, useEffect, useRef, useState } from 'react'

import {
  type ChannelInsights,
  getInsights,
  getViewerProfile,
  listViewers,
  type ViewerProfile,
  type ViewerSummary,
} from '@/api/analytics'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  Empty,
  EmptyDescription,
  Icon,
  Input,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  SlideUp,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const PERIODS = [
  { label: '7 天', value: '7' },
  { label: '30 天', value: '30' },
  { label: '90 天', value: '90' },
]

function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' })
}

function formatDateFull(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-TW', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

// ─── Summary Tiles ───────────────────────────────────────────────────────────

function SummaryTile({ icon, value, label }: { icon: string; value: string; label: string }) {
  return (
    <div className="rounded-md border bg-card px-3 py-2.5">
      <div className="flex items-center justify-between mb-1">
        <p className="text-xs text-muted-foreground">{label}</p>
        <Icon icon={icon} size="sm" wrapperClassName="text-muted-foreground/60" />
      </div>
      <p className="text-xl font-bold tabular-nums">{value}</p>
    </div>
  )
}

// ─── Viewer List ─────────────────────────────────────────────────────────────

interface ViewerRowProps {
  viewer: ViewerSummary
  rank: number
  onClick: () => void
}

function ViewerRow({ viewer, rank, onClick }: ViewerRowProps) {
  const name = viewer.display_name || viewer.username
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 rounded-md border bg-card px-3 py-2.5 hover:bg-accent transition-colors text-left"
    >
      <span className="text-xs font-mono text-muted-foreground w-5 shrink-0 text-right">
        {rank}
      </span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{name}</p>
        <p className="text-xs text-muted-foreground truncate">@{viewer.username}</p>
      </div>
      <div className="flex items-center gap-4 shrink-0">
        <Col value={viewer.total_messages.toLocaleString()} label="留言" />
        <Col value={String(viewer.sessions_attended)} label="場次" />
        <Col
          value={viewer.total_bits > 0 ? viewer.total_bits.toLocaleString() : '—'}
          label="小奇點"
          valueClassName={viewer.total_bits > 0 ? 'text-primary' : 'text-muted-foreground'}
        />
        <span className="text-xs text-muted-foreground w-12 text-right shrink-0 hidden sm:block">
          {formatDate(viewer.last_seen)}
        </span>
      </div>
    </button>
  )
}

function Col({
  value,
  label,
  valueClassName,
}: {
  value: string
  label: string
  valueClassName?: string
}) {
  return (
    <div className="w-14 text-right shrink-0">
      <p className={`text-sm font-bold tabular-nums ${valueClassName ?? ''}`}>{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

// ─── Viewer Sheet ─────────────────────────────────────────────────────────────

const EVENT_META: Record<string, { icon: string; label: string; color: string }> = {
  follow: { icon: 'fa-solid fa-heart', label: '追隨', color: 'text-rose-400' },
  subscribe: { icon: 'fa-solid fa-star', label: '訂閱', color: 'text-[var(--status-special)]' },
  cheer: { icon: 'fa-solid fa-gem', label: '小奇點', color: 'text-primary' },
}

const SUB_TIER_LABEL: Record<string, string> = {
  '1': '層級 1',
  '2': '層級 2',
  '3': '層級 3',
}

interface ViewerSheetProps {
  userId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  days: number
}

function StatusRow({
  icon,
  iconClass,
  children,
}: {
  icon: string
  iconClass: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3">
      <Icon icon={icon} size="sm" wrapperClassName={`shrink-0 ${iconClass}`} />
      <span className="text-sm text-foreground">{children}</span>
    </div>
  )
}

function StatTile({ icon, value, label }: { icon: string; value: string; label: string }) {
  return (
    <div className="rounded-md border bg-card p-3 flex flex-col gap-1.5">
      <Icon icon={icon} size="sm" wrapperClassName="text-primary/70" />
      <p className="text-lg font-bold tabular-nums leading-none">{value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  )
}

function ViewerSheet({ userId, open, onOpenChange, days }: ViewerSheetProps) {
  const [profile, setProfile] = useState<ViewerProfile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!userId || !open) return

    let cancelled = false
    getViewerProfile(userId, days)
      .then(data => {
        if (!cancelled) {
          setProfile(data)
          setLoading(false)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setProfile(null)
          setLoading(false)
        }
      })

    return () => {
      cancelled = true
      setProfile(null)
      setLoading(true)
    }
  }, [userId, open, days])

  const name = profile?.display_name || profile?.username || userId || '—'
  const username = profile?.username
  const twitch = profile?.twitch

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-90 p-0 overflow-y-auto flex flex-col">
        {/* Header */}
        <div className="px-5 pt-6 pb-4 border-b shrink-0">
          <SheetHeader className="text-left pr-8">
            {loading ? (
              <>
                <Skeleton className="h-5 w-36 mb-1" />
                <Skeleton className="h-4 w-24" />
              </>
            ) : (
              <>
                <SheetTitle className="text-base leading-snug">{name}</SheetTitle>
                {username && <SheetDescription className="text-xs">@{username}</SheetDescription>}
              </>
            )}
          </SheetHeader>
        </div>

        {loading ? (
          <div className="px-5 py-4 space-y-4 flex-1">
            <div className="space-y-3">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-40" />
            </div>
            <div className="grid grid-cols-3 gap-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-16 rounded-md" />
              ))}
            </div>
            <div className="space-y-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-9 rounded-md" />
              ))}
            </div>
          </div>
        ) : profile ? (
          <>
            {/* Follow / Sub status */}
            <div className="px-5 py-4 border-b space-y-3 shrink-0">
              <StatusRow icon="fa-solid fa-heart" iconClass="text-rose-400">
                {profile.follow_since ? (
                  <span>
                    自 <span className="font-medium">{formatDateFull(profile.follow_since)}</span>{' '}
                    開始追隨
                  </span>
                ) : (
                  <span className="text-muted-foreground">尚未追隨</span>
                )}
              </StatusRow>

              {twitch?.is_subscribed ? (
                <StatusRow icon="fa-solid fa-star" iconClass="text-[var(--status-special)]">
                  <span>
                    <span className="font-medium">
                      {SUB_TIER_LABEL[twitch.sub_tier ?? ''] ?? '訂閱中'}
                    </span>
                    {twitch.sub_gifted && (
                      <span className="ml-1 text-muted-foreground text-xs">（贈訂）</span>
                    )}
                  </span>
                </StatusRow>
              ) : (
                <StatusRow icon="fa-regular fa-star" iconClass="text-muted-foreground">
                  <span className="text-muted-foreground">尚未訂閱</span>
                </StatusRow>
              )}
            </div>

            {/* Stats */}
            <div className="px-5 py-4 border-b shrink-0">
              <div className="grid grid-cols-3 gap-3">
                <StatTile
                  icon="fa-solid fa-comments"
                  value={profile.total_messages.toLocaleString()}
                  label="留言次數"
                />
                <StatTile
                  icon="fa-solid fa-calendar-days"
                  value={String(profile.sessions_attended)}
                  label="出現場次"
                />
                <StatTile
                  icon="fa-solid fa-gem"
                  value={profile.total_bits > 0 ? profile.total_bits.toLocaleString() : '—'}
                  label="小奇點"
                />
              </div>
              <p className="text-xs text-muted-foreground mt-3">
                最後活躍：{formatDate(profile.last_seen)}
              </p>
            </div>

            {/* Events */}
            {profile.events.length > 0 && (
              <div className="px-5 py-4 flex-1">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2.5">
                  互動紀錄
                </p>
                <div className="space-y-1.5">
                  {profile.events.map((ev, i) => {
                    const meta = EVENT_META[ev.event_type] ?? {
                      icon: 'fa-solid fa-circle-info',
                      label: ev.event_type,
                      color: 'text-muted-foreground',
                    }
                    const bits =
                      ev.event_type === 'cheer'
                        ? (ev.metadata as { bits?: number })?.bits
                        : undefined
                    return (
                      <div key={i} className="flex items-center gap-3 py-1.5">
                        <Icon
                          icon={meta.icon}
                          size="sm"
                          wrapperClassName={`${meta.color} shrink-0`}
                        />
                        <span className="text-sm flex-1">
                          {meta.label}
                          {bits !== undefined && (
                            <span className="text-muted-foreground ml-1">× {bits}</span>
                          )}
                        </span>
                        <span className="text-xs text-muted-foreground shrink-0">
                          {formatDate(ev.occurred_at)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </>
        ) : (
          <p className="px-5 py-4 text-sm text-muted-foreground">無法載入觀眾資料</p>
        )}
      </SheetContent>
    </Sheet>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Insights() {
  useDocumentTitle('Insights')
  const { user, isInitialized } = useAuth()

  const [period, setPeriod] = useState('30')
  const [search, setSearch] = useState('')
  const [initialized, setInitialized] = useState(false)
  const [viewers, setViewers] = useState<ViewerSummary[]>([])
  const [insights, setInsights] = useState<ChannelInsights | null>(null)
  const [insightsLoading, setInsightsLoading] = useState(true)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const loadedForRef = useRef<string | null>(null)

  const fetchViewers = useCallback(
    async (days: number) => {
      if (!user) return
      try {
        setViewers(await listViewers(days))
      } catch {
        setViewers([])
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
    fetchViewers(days)
    fetchInsights(days)
  }, [isInitialized, user, period, fetchViewers, fetchInsights])

  const handlePeriodChange = (value: string) => {
    if (value === period) return
    loadedForRef.current = null
    setPeriod(value)
  }

  const filtered = viewers.filter(v => {
    if (!search.trim()) return true
    const q = search.toLowerCase()
    return (v.display_name ?? '').toLowerCase().includes(q) || v.username.toLowerCase().includes(q)
  })

  return (
    <PageMain>
      <PageHeader title="Insights" description="觀眾互動與活躍度數據" />

      <SlideUp inView>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {insightsLoading ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-md" />
            ))
          ) : (
            <>
              <SummaryTile
                icon="fa-solid fa-comments"
                value={insights?.total_messages.toLocaleString() ?? '—'}
                label="聊天訊息"
              />
              <SummaryTile
                icon="fa-solid fa-heart"
                value={insights?.total_follows.toLocaleString() ?? '—'}
                label="新追隨"
              />
              <SummaryTile
                icon="fa-solid fa-star"
                value={insights?.total_subs.toLocaleString() ?? '—'}
                label="新訂閱"
              />
              <SummaryTile
                icon="fa-solid fa-gem"
                value={insights?.total_bits > 0 ? insights.total_bits.toLocaleString() : '—'}
                label="小奇點"
              />
            </>
          )}
        </div>
      </SlideUp>

      <SlideUp inView>
        <div className="flex items-center gap-3 flex-wrap">
          <Tabs value={period} onValueChange={handlePeriodChange}>
            <TabsList>
              {PERIODS.map(p => (
                <TabsTrigger key={p.value} value={p.value}>
                  {p.label}
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
          <Input
            placeholder="搜尋觀眾..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-44 h-9"
          />
        </div>
      </SlideUp>

      <SlideUp inView>
        {!initialized ? (
          <div className="space-y-1.5">
            {Array.from({ length: 8 }).map((_, i) => (
              <Skeleton key={i} className="h-12 w-full rounded-md" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <Empty className="border-none py-16">
            <EmptyDescription>
              {search ? '找不到符合的觀眾' : '直播結束後才會更新觀眾資料'}
            </EmptyDescription>
          </Empty>
        ) : (
          <div className="space-y-1">
            {filtered.map((v, i) => (
              <ViewerRow
                key={v.user_id}
                viewer={v}
                rank={i + 1}
                onClick={() => setSelectedUserId(v.user_id)}
              />
            ))}
          </div>
        )}
      </SlideUp>

      <ViewerSheet
        userId={selectedUserId}
        open={selectedUserId !== null}
        onOpenChange={open => {
          if (!open) setSelectedUserId(null)
        }}
        days={Number(period)}
      />
    </PageMain>
  )
}
