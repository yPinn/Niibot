import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react'

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
  SheetSection,
  SheetTitle,
  Skeleton,
  SlideUp,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
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

function formatDuration(seconds: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const hh = String(h).padStart(2, '0')
  const mm = String(m).padStart(2, '0')
  return d > 0 ? `${d}/${hh}:${mm}` : `${hh}:${mm}`
}

function formatCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

// ─── Summary Tiles ───────────────────────────────────────────────────────────

function SummaryTile({
  icon,
  value,
  label,
  iconClassName,
}: {
  icon: string
  value: string
  label: string
  iconClassName?: string
}) {
  return (
    <div className="rounded-md border bg-card px-3 py-2.5">
      <div className="flex items-center justify-between mb-1">
        <p className="text-label text-muted-foreground">{label}</p>
        <Icon
          icon={icon}
          size="sm"
          wrapperClassName={iconClassName ?? 'text-muted-foreground/60'}
        />
      </div>
      <p className="text-section-title font-bold tabular-nums">{value}</p>
    </div>
  )
}

// ─── Viewer List ─────────────────────────────────────────────────────────────

// Mobile:  rank | name | bits | messages            (2 data cols)
// sm+:     +sessions +watch                          (4 data cols)
// lg+:     +last_seen                               (5 data cols)
const ROW_GRID =
  'grid-cols-[1.25rem_minmax(0,1fr)_6rem_6rem] sm:grid-cols-[1.25rem_minmax(0,1fr)_repeat(4,6rem)] lg:grid-cols-[1.25rem_minmax(0,1fr)_repeat(5,6rem)]'

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
      className={`w-full grid items-center gap-3 rounded-md border bg-card px-3 py-2.5 hover:bg-accent transition-colors text-left ${ROW_GRID}`}
    >
      <span className="text-sub font-mono font-semibold text-muted-foreground text-right">
        {rank}
      </span>
      <div className="min-w-0">
        <p className="text-sub font-medium truncate">{name}</p>
        <p className="text-label text-muted-foreground truncate">@{viewer.username}</p>
      </div>
      <Col
        value={viewer.total_bits > 0 ? viewer.total_bits.toLocaleString() : '—'}
        label="小奇點"
        valueClassName={viewer.total_bits > 0 ? 'text-primary' : 'text-muted-foreground'}
      />
      <Col value={viewer.total_messages.toLocaleString()} label="留言" />
      <Col value={String(viewer.sessions_attended)} label="場次" className="hidden sm:block" />
      <Col value={formatDuration(viewer.watch_seconds)} label="時長" className="hidden sm:block" />
      <span className="text-label text-muted-foreground text-right hidden lg:block">
        {formatDate(viewer.last_seen)}
      </span>
    </button>
  )
}

function Col({
  value,
  label,
  valueClassName,
  className,
}: {
  value: string
  label: string
  valueClassName?: string
  className?: string
}) {
  return (
    <div className={`text-right ${className ?? ''}`}>
      <p className={`text-sub font-bold tabular-nums ${valueClassName ?? ''}`}>{value}</p>
      <p className="text-label text-muted-foreground">{label}</p>
    </div>
  )
}

// ─── Viewer Sheet ─────────────────────────────────────────────────────────────

const EVENT_META: Record<string, { icon: string; label: string; color: string }> = {
  follow: { icon: 'fa-solid fa-heart', label: '追隨', color: 'text-rose-400' },
  subscribe: { icon: 'fa-solid fa-star', label: '訂閱', color: 'text-status-special' },
  cheer: { icon: 'fa-solid fa-diamond-half-stroke', label: '小奇點', color: 'text-primary' },
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

function PartnerBadge() {
  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="shrink-0 inline-flex">
            <Icon icon="fa-solid fa-circle-check" size="sm" wrapperClassName="text-primary" />
          </span>
        </TooltipTrigger>
        <TooltipContent>合作夥伴</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
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
      <span className="text-sub text-foreground">{children}</span>
    </div>
  )
}

function StatTile({
  icon,
  value,
  label,
  tooltip,
}: {
  icon: string
  value: string
  label: string
  tooltip?: string
}) {
  const inner = (
    <div className="rounded-md border bg-card p-3 flex flex-col gap-1.5">
      <p className="text-label text-muted-foreground">{label}</p>
      <div className="flex items-end justify-between">
        <p className="text-card-title font-bold tabular-nums leading-none">{value}</p>
        <Icon icon={icon} size="sm" wrapperClassName="text-primary/70" />
      </div>
    </div>
  )

  if (!tooltip) return inner

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

type ViewerSheetState = { profile: ViewerProfile | null; loading: boolean }
type ViewerSheetAction =
  | { type: 'reset' }
  | { type: 'success'; payload: ViewerProfile }
  | { type: 'error' }

function viewerSheetReducer(_: ViewerSheetState, action: ViewerSheetAction): ViewerSheetState {
  if (action.type === 'reset') return { profile: null, loading: true }
  if (action.type === 'success') return { profile: action.payload, loading: false }
  return { profile: null, loading: false }
}

function ViewerSheet({ userId, open, onOpenChange, days }: ViewerSheetProps) {
  const [{ profile, loading }, dispatch] = useReducer(viewerSheetReducer, {
    profile: null,
    loading: true,
  })

  useEffect(() => {
    if (!userId || !open) return

    let cancelled = false
    dispatch({ type: 'reset' })
    getViewerProfile(userId, days)
      .then(data => {
        if (!cancelled) dispatch({ type: 'success', payload: data })
      })
      .catch(() => {
        if (!cancelled) dispatch({ type: 'error' })
      })

    return () => {
      cancelled = true
    }
  }, [userId, open, days])

  const name = profile?.display_name || profile?.username || userId || '—'
  const username = profile?.username
  const twitch = profile?.twitch

  const isPartner = profile?.broadcaster_type === 'partner'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-90 p-0 overflow-y-auto flex flex-col select-none">
        {/* Header */}
        {loading ? (
          <SheetHeader className="pr-10 shrink-0">
            <SheetTitle className="sr-only">載入觀眾資料</SheetTitle>
            <SheetDescription className="sr-only">正在載入</SheetDescription>
            <div className="flex items-center gap-3">
              <Skeleton className="h-11 w-11 rounded-full shrink-0" />
              <div className="space-y-1.5 flex-1 min-w-0">
                <Skeleton className="h-5 w-36" />
                <Skeleton className="h-4 w-24" />
              </div>
            </div>
          </SheetHeader>
        ) : profile?.offline_image_url ? (
          /* ── Banner mode: plain div so SheetHeader's p-page doesn't create gaps ── */
          <div className="shrink-0">
            <SheetTitle className="sr-only">{name}</SheetTitle>
            <SheetDescription className="sr-only">
              {username ? `@${username}` : '觀眾資料'}
            </SheetDescription>
            <div className="relative">
              <img
                src={profile.offline_image_url}
                alt=""
                className="w-full h-24 object-cover object-center"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-transparent" />
            </div>
            <div className="relative z-10 flex items-end gap-3 px-page pb-3 pr-12 -mt-8">
              <div className="shrink-0 relative z-10">
                {profile.profile_image_url ? (
                  <img
                    src={profile.profile_image_url}
                    alt={name}
                    className="h-16 w-16 rounded-full object-cover ring-2 ring-background"
                  />
                ) : (
                  <div className="h-16 w-16 rounded-full bg-muted ring-2 ring-background flex items-center justify-center text-sub font-bold text-muted-foreground select-none">
                    {name.charAt(0).toUpperCase()}
                  </div>
                )}
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold leading-snug truncate select-text">
                    {name}
                  </span>
                  {isPartner && <PartnerBadge />}
                </div>
                <p className="text-label text-muted-foreground mt-0.5">
                  {username ? (
                    <a
                      href={`https://twitch.tv/${username}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="select-text hover:text-foreground hover:underline transition-colors"
                    >
                      @{username}
                    </a>
                  ) : (
                    '觀眾資料'
                  )}
                </p>
              </div>
            </div>
          </div>
        ) : (
          /* ── No banner mode ── */
          <SheetHeader className="pr-10 shrink-0">
            <div className="flex items-center gap-3">
              {profile?.profile_image_url ? (
                <img
                  src={profile.profile_image_url}
                  alt={name}
                  className="h-11 w-11 rounded-full shrink-0 object-cover"
                />
              ) : (
                <div className="h-11 w-11 rounded-full shrink-0 bg-muted flex items-center justify-center text-sub font-bold text-muted-foreground select-none">
                  {name.charAt(0).toUpperCase()}
                </div>
              )}
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <SheetTitle className="text-base leading-snug select-text">{name}</SheetTitle>
                  {isPartner && <PartnerBadge />}
                </div>
                <SheetDescription className="text-label mt-0.5">
                  {username ? (
                    <a
                      href={`https://twitch.tv/${username}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="select-text hover:text-foreground hover:underline transition-colors"
                    >
                      @{username}
                    </a>
                  ) : (
                    '觀眾資料'
                  )}
                </SheetDescription>
              </div>
            </div>
          </SheetHeader>
        )}

        {loading ? (
          <SheetSection className="space-y-4 flex-1">
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
          </SheetSection>
        ) : profile ? (
          <>
            {/* Follow / Sub / Role / Ban status */}
            <SheetSection className="space-y-3">
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
                <StatusRow icon="fa-solid fa-star" iconClass="text-status-special">
                  <span className="font-medium">
                    {SUB_TIER_LABEL[twitch.sub_tier ?? ''] ?? '訂閱中'}
                  </span>
                  {twitch.sub_gifted && (
                    <span className="ml-1 text-muted-foreground text-label">
                      {twitch.sub_gifter ? `・由 @${twitch.sub_gifter} 贈送` : '・贈禮訂閱'}
                    </span>
                  )}
                </StatusRow>
              ) : (
                <StatusRow icon="fa-regular fa-star" iconClass="text-muted-foreground">
                  <span className="text-muted-foreground">尚未訂閱</span>
                </StatusRow>
              )}
              {twitch?.is_mod && (
                <StatusRow icon="fa-solid fa-sword" iconClass="text-status-success">
                  <span className="font-medium">頻道管理員</span>
                </StatusRow>
              )}
              {twitch?.is_vip && (
                <StatusRow icon="fa-solid fa-gem" iconClass="text-[#e005b9]">
                  <span className="font-medium">VIP</span>
                </StatusRow>
              )}
              {twitch?.is_banned && (
                <StatusRow icon="fa-solid fa-ban" iconClass="text-destructive">
                  {twitch.ban_expires_at ? (
                    <span>
                      封禁至{' '}
                      <span className="font-medium">{formatDateFull(twitch.ban_expires_at)}</span>
                      {twitch.ban_reason && (
                        <span className="text-muted-foreground ml-1">（{twitch.ban_reason}）</span>
                      )}
                    </span>
                  ) : (
                    <span>
                      永久封禁
                      {twitch.ban_reason && (
                        <span className="text-muted-foreground ml-1">（{twitch.ban_reason}）</span>
                      )}
                    </span>
                  )}
                </StatusRow>
              )}
            </SheetSection>

            {/* Stats */}
            <SheetSection>
              <div className="grid grid-cols-2 gap-3">
                <StatTile
                  icon="fa-solid fa-diamond-half-stroke"
                  value={profile.total_bits > 0 ? formatCompact(profile.total_bits) : '—'}
                  label="小奇點"
                  tooltip={
                    profile.total_bits >= 1_000 ? profile.total_bits.toLocaleString() : undefined
                  }
                />
                <StatTile
                  icon="fa-solid fa-comments"
                  value={formatCompact(profile.total_messages)}
                  label="留言次數"
                  tooltip={
                    profile.total_messages >= 1_000
                      ? profile.total_messages.toLocaleString()
                      : undefined
                  }
                />
                <StatTile
                  icon="fa-solid fa-calendar-days"
                  value={formatCompact(profile.sessions_attended)}
                  label="出現場次"
                />
                <StatTile
                  icon="fa-solid fa-clock"
                  value={profile.watch_seconds > 0 ? formatDuration(profile.watch_seconds) : '—'}
                  label="觀看時長"
                  tooltip={
                    profile.watch_seconds >= 3600
                      ? `${Math.floor(profile.watch_seconds / 60).toLocaleString()} 分鐘`
                      : undefined
                  }
                />
              </div>
              <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
                <p className="text-label text-muted-foreground">
                  最後活躍：{formatDate(profile.last_seen)}
                </p>
                {twitch?.bits_rank != null && (
                  <p className="text-label text-muted-foreground">
                    小奇點排名：
                    <span className="font-medium text-foreground">#{twitch.bits_rank}</span>
                  </p>
                )}
                {profile.account_created_at && (
                  <p className="text-label text-muted-foreground">
                    帳號建立：{formatDateFull(profile.account_created_at)}
                  </p>
                )}
              </div>
            </SheetSection>

            {/* Events */}
            {profile.events.length > 0 && (
              <SheetSection title="互動紀錄" className="flex-1">
                <div className="space-y-1.5">
                  {profile.events.map(ev => {
                    const meta = EVENT_META[ev.event_type] ?? {
                      icon: 'fa-solid fa-circle-info',
                      label: ev.event_type,
                      color: 'text-muted-foreground',
                    }
                    const bits =
                      ev.event_type === 'cheer'
                        ? (ev.metadata as { bits?: number })?.bits
                        : undefined
                    const subMeta =
                      ev.event_type === 'subscribe'
                        ? (ev.metadata as {
                            tier?: string
                            is_gift?: boolean
                            gift_count?: number
                          } | null)
                        : undefined
                    const subTierLabel = subMeta?.tier
                      ? (SUB_TIER_LABEL[String(Number(subMeta.tier) / 1000)] ?? null)
                      : null
                    const isGift = subMeta?.is_gift === true
                    const giftCount = isGift ? (subMeta?.gift_count ?? null) : null
                    const rowIcon = isGift ? 'fa-solid fa-gift' : meta.icon
                    const rowColor = isGift ? 'text-status-special' : meta.color
                    const rowLabel = isGift ? '贈禮訂閱' : meta.label
                    return (
                      <div
                        key={`${ev.occurred_at}-${ev.event_type}`}
                        className="flex items-center gap-3 py-1.5"
                      >
                        <Icon icon={rowIcon} size="sm" wrapperClassName={`${rowColor} shrink-0`} />
                        <span className="text-sub flex-1 flex items-center gap-1.5">
                          {rowLabel}
                          {subTierLabel && (
                            <span className="text-muted-foreground">({subTierLabel})</span>
                          )}
                          {giftCount != null && (
                            <>
                              <span className="text-muted-foreground">×</span>
                              <span>{giftCount}</span>
                            </>
                          )}
                          {bits !== undefined && (
                            <>
                              <span className="text-muted-foreground">×</span>
                              <span>{bits.toLocaleString()}</span>
                            </>
                          )}
                        </span>
                        <span className="text-label text-muted-foreground shrink-0">
                          {formatDate(ev.occurred_at)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </SheetSection>
            )}
          </>
        ) : (
          <SheetSection>
            <p className="text-sub text-muted-foreground">無法載入觀眾資料</p>
          </SheetSection>
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
  const [sort, setSort] = useState<'messages' | 'watch' | 'bits' | 'sessions' | 'last_seen'>('bits')
  const [sortDir, setSortDir] = useState<'desc' | 'asc'>('desc')
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

  const SORT_COLS = [
    {
      key: 'bits',
      label: '小奇點',
      icon: 'fa-solid fa-diamond-half-stroke',
      natural: 'desc',
      show: '',
    },
    { key: 'messages', label: '留言次數', icon: 'fa-solid fa-comment', natural: 'desc', show: '' },
    {
      key: 'sessions',
      label: '出現場次',
      icon: 'fa-solid fa-calendar-days',
      natural: 'desc',
      show: 'hidden sm:flex',
    },
    {
      key: 'watch',
      label: '觀看時長',
      icon: 'fa-solid fa-clock',
      natural: 'desc',
      show: 'hidden sm:flex',
    },
    {
      key: 'last_seen',
      label: '最後出現',
      icon: 'fa-solid fa-hourglass-end',
      natural: 'desc',
      show: 'hidden lg:flex',
    },
  ] as const

  const handleSort = (key: typeof sort) => {
    if (sort === key) {
      setSortDir(d => (d === 'desc' ? 'asc' : 'desc'))
    } else {
      const col = SORT_COLS.find(c => c.key === key)!
      setSort(key)
      setSortDir(col.natural as 'desc' | 'asc')
    }
  }

  const filtered = React.useMemo(() => {
    const q = search.trim().toLowerCase()
    return viewers
      .filter(v => {
        if (!q) return true
        return (
          (v.display_name ?? '').toLowerCase().includes(q) || v.username.toLowerCase().includes(q)
        )
      })
      .sort((a, b) => {
        const dir = sortDir === 'desc' ? 1 : -1
        switch (sort) {
          case 'messages':
            return dir * (b.total_messages - a.total_messages)
          case 'watch':
            return dir * (b.watch_seconds - a.watch_seconds)
          case 'bits':
            return dir * (b.total_bits - a.total_bits)
          case 'sessions':
            return dir * (b.sessions_attended - a.sessions_attended)
          case 'last_seen': {
            if (!a.last_seen && !b.last_seen) return 0
            if (!a.last_seen) return 1
            if (!b.last_seen) return -1
            return dir * b.last_seen.localeCompare(a.last_seen)
          }
        }
      })
  }, [viewers, search, sort, sortDir])

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
                iconClassName="text-status-info/80"
              />
              <SummaryTile
                icon="fa-solid fa-heart"
                value={insights?.total_follows.toLocaleString() ?? '—'}
                label="新追隨"
                iconClassName="text-rose-400/80"
              />
              <SummaryTile
                icon="fa-solid fa-star"
                value={insights?.total_subs.toLocaleString() ?? '—'}
                label="新訂閱"
                iconClassName="text-primary/80"
              />
              <SummaryTile
                icon="fa-solid fa-diamond-half-stroke"
                value={
                  insights && insights.total_bits > 0 ? insights.total_bits.toLocaleString() : '—'
                }
                label="小奇點"
                iconClassName="text-primary/80"
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
            <div
              className={`grid items-center gap-3 px-3 pb-1 border border-transparent text-label text-muted-foreground ${ROW_GRID}`}
            >
              <span />
              <span>觀眾</span>
              {SORT_COLS.map(col => {
                const active = sort === col.key
                return (
                  <button
                    key={col.key}
                    type="button"
                    onClick={() => handleSort(col.key)}
                    className={[
                      'items-center justify-end gap-1 rounded pl-1 pr-0 py-0.5 transition-colors',
                      col.show || 'flex',
                      active ? 'text-foreground font-medium' : 'hover:text-foreground',
                    ].join(' ')}
                  >
                    <i className={`${col.icon} text-[10px]`} />
                    {col.label}
                    <i
                      className={[
                        'fa-solid text-[9px] transition-opacity',
                        active
                          ? sortDir === 'desc'
                            ? 'fa-arrow-down opacity-100'
                            : 'fa-arrow-up opacity-100'
                          : 'fa-sort opacity-30',
                      ].join(' ')}
                    />
                  </button>
                )
              })}
            </div>
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
        key={`${selectedUserId}-${period}`}
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
