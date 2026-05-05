import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import {
  CartesianGrid,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  type ChannelInsights,
  getInsights,
  getViewerProfile,
  listViewers,
  type ViewerProfile,
  type ViewerSummary,
} from '@/api/analytics'
import { PageMain } from '@/components/PageMain'
import {
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Icon,
  Input,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Skeleton,
  SlideUp,
  SlideUpSm,
  Stagger,
  StaggerItem,
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
import { cn } from '@/lib/utils'

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
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
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
    <div className="rounded-md border px-3 py-2.5">
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

const ROW_GRID = 'grid-cols-[1.25rem_minmax(0,1fr)_5.5rem_5.5rem_5.5rem]'

const RANK_STYLES = {
  1: {
    gradient: 'bg-gradient-to-r from-amber-400/15',
    border: 'border-amber-400/30',
    icon: 'fa-solid fa-trophy',
    color: 'text-amber-400',
  },
  2: {
    gradient: 'bg-gradient-to-r from-slate-400/15',
    border: 'border-slate-400/30',
    icon: 'fa-solid fa-medal',
    color: 'text-slate-400',
  },
  3: {
    gradient: 'bg-gradient-to-r from-orange-400/15',
    border: 'border-orange-400/30',
    icon: 'fa-solid fa-medal',
    color: 'text-orange-400',
  },
} as const

interface ViewerRowProps {
  viewer: ViewerSummary
  rank: number
  isHovered: boolean
  onClick: () => void
  onHover: (id: string | null) => void
}

function ViewerRow({ viewer, rank, isHovered, onClick, onHover }: ViewerRowProps) {
  const name = viewer.display_name || viewer.username
  const top = rank <= 3 ? RANK_STYLES[rank as 1 | 2 | 3] : null
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => onHover(viewer.user_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        'w-full grid items-center gap-3 rounded-md border px-3 py-2.5 hover:bg-accent transition-colors text-left',
        ROW_GRID,
        top && `${top.gradient} ${top.border}`,
        isHovered && 'ring-1 ring-inset ring-primary/40'
      )}
    >
      {top ? (
        <span className={`flex justify-center ${top.color}`}>
          <i className={`${top.icon} text-[11px]`} />
        </span>
      ) : (
        <span className="text-sub font-mono font-semibold text-muted-foreground text-right">
          {rank}
        </span>
      )}
      <div className="min-w-0">
        <p className="text-sub font-medium truncate">{name}</p>
        <p className="text-label text-muted-foreground truncate">@{viewer.username}</p>
      </div>
      <Col value={viewer.total_messages.toLocaleString()} />
      <Col value={formatDuration(viewer.watch_seconds)} />
      <Col value={viewer.engagement_score.toFixed(1)} valueClassName="text-primary" />
    </button>
  )
}

function Col({
  value,
  valueClassName,
  className,
}: {
  value: string
  valueClassName?: string
  className?: string
}) {
  return (
    <div className={`text-right ${className ?? ''}`}>
      <p className={`text-sub font-bold tabular-nums ${valueClassName ?? ''}`}>{value}</p>
    </div>
  )
}

// ─── Viewer List Component ───────────────────────────────────────────────────

interface ViewerListProps {
  filtered: ViewerSummary[]
  sort: SortKey
  sortDir: 'desc' | 'asc'
  search: string
  hoveredUserId: string | null
  onSort: (key: SortKey) => void
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
}

function ViewerList({
  filtered,
  sort,
  sortDir,
  search,
  hoveredUserId,
  onSort,
  onSelect,
  onHover,
}: ViewerListProps) {
  if (filtered.length === 0) {
    return (
      <Empty className="border-none py-16">
        <EmptyHeader>
          <EmptyMedia>
            <Icon
              icon={search ? 'fa-solid fa-magnifying-glass' : 'fa-solid fa-users'}
              wrapperClassName="size-20 opacity-25"
              className="text-[5rem]"
            />
          </EmptyMedia>
          <EmptyTitle>{search ? '找不到符合的觀眾' : '尚無觀眾資料'}</EmptyTitle>
          {!search && (
            <EmptyDescription>每場直播結束後會累積觀眾資料，歷史紀錄可在此查閱</EmptyDescription>
          )}
        </EmptyHeader>
      </Empty>
    )
  }
  return (
    <div className="flex flex-col">
      <div
        className={`grid items-center gap-3 px-3 pb-1 border border-transparent text-label text-muted-foreground shrink-0 ${ROW_GRID}`}
      >
        <span />
        <span>觀眾</span>
        {SORT_COLS.map(col => {
          const active = sort === col.key
          return (
            <button
              key={col.key}
              type="button"
              onClick={() => onSort(col.key)}
              className={cn(
                'flex items-center justify-end gap-1 rounded pl-1 pr-0 py-0.5 transition-colors',
                active ? 'text-foreground font-medium' : 'hover:text-foreground'
              )}
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
      <div className="max-h-[646px] overflow-y-auto scrollbar space-y-1 pr-0.5">
        {filtered.map((v, i) => (
          <ViewerRow
            key={v.user_id}
            viewer={v}
            rank={i + 1}
            isHovered={hoveredUserId === v.user_id}
            onClick={() => onSelect(v.user_id)}
            onHover={onHover}
          />
        ))}
      </div>
    </div>
  )
}

// ─── Viewer Scatter Chart ─────────────────────────────────────────────────────

type DotData = {
  x: number
  y: number
  score: number
  name: string
  user_id: string
  dotFill: string
}
type AxisTick = { x: string | number; y: string | number; payload: { value: number } }

function ScatterTooltip({
  active,
  payload,
}: {
  active?: boolean
  payload?: { payload: DotData }[]
}) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const mins = d.x
  const watchLabel = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`
  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-popover-foreground shadow-sm space-y-0.5">
      <p className="text-sub font-medium">{d.name}</p>
      <p className="text-label text-muted-foreground">
        留言 {d.y.toLocaleString()} · {watchLabel}
      </p>
      <p className="text-label text-primary">活躍度 {d.score.toFixed(1)}</p>
    </div>
  )
}

function ViewerScatterChart({
  viewers,
  hoveredUserId,
  onHover,
}: {
  viewers: ViewerSummary[]
  hoveredUserId: string | null
  onHover: (id: string | null) => void
}) {
  const data = viewers.map(v => {
    const score = v.engagement_score
    const dotFill =
      score >= 60
        ? 'var(--chart-1)' // theme purple
        : score >= 20
          ? 'var(--chart-5)' // theme blue
          : 'var(--muted-foreground)' // theme muted
    return {
      x: Math.round(v.watch_seconds / 60),
      y: v.total_messages,
      score,
      name: v.display_name || v.username,
      user_id: v.user_id,
      dotFill,
    }
  })

  const shape = useCallback(
    ({ cx, cy, payload }: { cx?: number; cy?: number; payload?: DotData }) => {
      if (cx == null || cy == null || !payload) return null
      const isHovered = hoveredUserId != null && payload.user_id === hoveredUserId
      const isDimmed = hoveredUserId != null && payload.user_id !== hoveredUserId
      return (
        <circle
          cx={cx}
          cy={cy}
          r={isHovered ? 9 : 6}
          style={{
            fill: payload.dotFill,
            opacity: isDimmed ? 0.2 : 1,
            transition: 'opacity 0.15s ease',
          }}
          onMouseEnter={() => onHover(payload.user_id)}
          onMouseLeave={() => onHover(null)}
        />
      )
    },
    [hoveredUserId, onHover]
  )

  return (
    <div className="flex flex-col gap-element">
      <div className="flex items-center justify-between">
        <p className="text-label text-muted-foreground">觀眾分佈</p>
        <p className="text-label text-muted-foreground/60">觀看時長 × 留言數</p>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ScatterChart margin={{ top: 4, right: 8, bottom: 8, left: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(128,128,128,0.15)" />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, 'auto']}
            tick={({ x, y, payload }: AxisTick) => (
              <text
                x={x}
                y={Number(y) + 10}
                textAnchor="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 10 }}
              >
                {payload.value === 0
                  ? '0'
                  : payload.value >= 60
                    ? `${Math.floor(payload.value / 60)}h`
                    : `${payload.value}m`}
              </text>
            )}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            dataKey="y"
            type="number"
            domain={[0, 'auto']}
            tick={({ x, y, payload }: AxisTick) => (
              <text
                x={Number(x) - 2}
                y={y}
                textAnchor="end"
                dominantBaseline="middle"
                className="fill-muted-foreground"
                style={{ fontSize: 10 }}
              >
                {formatCompact(payload.value)}
              </text>
            )}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <RechartsTooltip
            content={<ScatterTooltip />}
            cursor={{ strokeDasharray: '3 3', stroke: 'rgba(128,128,128,0.3)' }}
          />
          <Scatter data={data} shape={shape} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  )
}

// ─── Viewer Sheet ─────────────────────────────────────────────────────────────

const EVENT_META: Record<string, { icon: string; label: string; color: string }> = {
  follow: { icon: 'fa-solid fa-heart', label: '追隨', color: 'text-rose-400' },
  subscribe: { icon: 'fa-solid fa-star', label: '訂閱', color: 'text-status-special' },
  cheer: { icon: 'fa-solid fa-diamond-half-stroke', label: '小奇點', color: 'text-primary' },
  raid: { icon: 'fa-solid fa-parachute-box', label: '揪團', color: 'text-status-info' },
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
  badge,
}: {
  icon: string
  value: string
  label: string
  tooltip?: string
  badge?: string
}) {
  const inner = (
    <div className="rounded-md border bg-card p-3 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <p className="text-label text-muted-foreground">{label}</p>
        {badge != null && (
          <span className="text-label text-muted-foreground tabular-nums border rounded-sm px-1.5 py-0.5 leading-none">
            {badge}
          </span>
        )}
      </div>
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
      <SheetContent className="w-full sm:max-w-sm p-0 overflow-y-auto flex flex-col select-none">
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
              <div className="absolute inset-0 bg-linear-to-t from-background via-background/60 to-transparent" />
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
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[73px] rounded-md" />
              ))}
            </div>
            <div className="space-y-1.5">
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
                {(() => {
                  const totalGifts = profile.events.reduce((sum, ev) => {
                    if (ev.event_type !== 'subscribe') return sum
                    const meta = ev.metadata as { is_gift?: boolean; gift_count?: number } | null
                    if (!meta?.is_gift) return sum
                    return sum + (meta.gift_count ?? 1)
                  }, 0)
                  return (
                    <StatTile
                      icon="fa-solid fa-gift"
                      value={totalGifts > 0 ? totalGifts.toLocaleString() : '—'}
                      label="贈禮訂閱"
                    />
                  )
                })()}
                <StatTile
                  icon="fa-solid fa-clock"
                  value={profile.watch_seconds > 0 ? formatDuration(profile.watch_seconds) : '—'}
                  label="觀看時長"
                  badge={`${profile.sessions_attended} 場`}
                  tooltip={
                    profile.watch_seconds >= 3600
                      ? `${Math.floor(profile.watch_seconds / 60).toLocaleString()} 分鐘`
                      : undefined
                  }
                />
              </div>
              <div className="flex flex-col gap-y-1 mt-3">
                <p className="text-label text-muted-foreground">
                  最後活躍：{formatDateFull(profile.last_seen)}
                </p>
                {profile.account_created_at && (
                  <p className="text-label text-muted-foreground">
                    帳號建立：{formatDateFull(profile.account_created_at)}
                  </p>
                )}
                {twitch?.bits_rank != null && (
                  <p className="text-label text-muted-foreground">
                    小奇點排名：
                    <span className="font-medium text-foreground">#{twitch.bits_rank}</span>
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
                    const raidViewers =
                      ev.event_type === 'raid'
                        ? (ev.metadata as { viewers?: number; from_broadcaster_name?: string })
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
                          {raidViewers?.viewers != null && (
                            <span className="text-muted-foreground">
                              ({raidViewers.viewers.toLocaleString()} 人)
                            </span>
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

const SORT_COLS = [
  { key: 'messages', label: '留言', icon: 'fa-solid fa-comment', natural: 'desc' },
  { key: 'watch', label: '時長', icon: 'fa-solid fa-clock', natural: 'desc' },
  { key: 'score', label: '活躍度', icon: 'fa-solid fa-fire', natural: 'desc' },
] as const

type SortKey = (typeof SORT_COLS)[number]['key']

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function Insights() {
  useDocumentTitle('Insights')
  const { user, isInitialized } = useAuth()

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
  const [hoveredUserId, setHoveredUserId] = useState<string | null>(null)
  const loadedForRef = useRef<string | null>(null)

  const fetchViewers = useCallback(
    async (days: number) => {
      if (!user) return
      try {
        setViewersError(false)
        setViewers(await listViewers(days))
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
    fetchViewers(days)
    fetchInsights(days)
  }, [isInitialized, user, period, fetchViewers, fetchInsights])

  const handlePeriodChange = (value: string) => {
    if (value === period) return
    loadedForRef.current = null
    setInitialized(false)
    setViewersError(false)
    setPeriod(value)
  }

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
          case 'score':
            return dir * (b.engagement_score - a.engagement_score)
        }
      })
  }, [viewers, search, sort, sortDir])

  return (
    <PageMain>
      {/* Header: title left, period tabs right */}
      <SlideUpSm inView>
        <h1 className="text-page-title font-bold">Insights</h1>
        <p className="text-sub text-muted-foreground mt-0.5">觀眾互動與活躍度數據</p>
      </SlideUpSm>

      {/* Main 2-col layout */}
      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-2 lg:items-start gap-section"
      >
        {/* Left: sticky – chart + summary cards */}
        <div className="rounded-lg border bg-card p-4 lg:sticky lg:top-page-lg flex flex-col gap-section">
          {!initialized ? (
            <Skeleton className="hidden lg:block h-[330px] rounded-md" />
          ) : viewers.length > 0 ? (
            <div className="hidden lg:block rounded-md bg-muted/20 p-3 [&_*]:outline-none">
              <ViewerScatterChart
                viewers={viewers}
                hoveredUserId={hoveredUserId}
                onHover={setHoveredUserId}
              />
            </div>
          ) : null}
          {(!initialized || viewers.length > 0) && <Separator className="hidden lg:block" />}
          <Stagger key={insightsLoading ? 'l' : 'd'} className="grid grid-cols-2 gap-section">
            {insightsLoading ? (
              Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-[69px] rounded-md" />
              ))
            ) : (
              <>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-diamond-half-stroke"
                    value={
                      insights && insights.total_bits > 0
                        ? insights.total_bits.toLocaleString()
                        : '—'
                    }
                    label="小奇點"
                    iconClassName="text-primary/80"
                  />
                </StaggerItem>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-star"
                    value={insights?.total_subs.toLocaleString() ?? '—'}
                    label="新訂閱"
                    iconClassName="text-primary/80"
                  />
                </StaggerItem>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-heart"
                    value={insights?.total_follows.toLocaleString() ?? '—'}
                    label="新追隨"
                    iconClassName="text-rose-400/80"
                  />
                </StaggerItem>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-comments"
                    value={insights?.total_messages.toLocaleString() ?? '—'}
                    label="聊天訊息"
                    iconClassName="text-status-info/80"
                  />
                </StaggerItem>
              </>
            )}
          </Stagger>
        </div>

        {/* Right: search + viewer list (~10 rows) */}
        <div className="rounded-lg border bg-card p-4 flex flex-col gap-section">
          <div className="flex items-center gap-element self-end shrink-0">
            <Input
              placeholder="搜尋觀眾..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="h-9 w-44"
            />
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
          {!initialized ? (
            <div className="space-y-1">
              {Array.from({ length: 10 }).map((_, i) => (
                <Skeleton key={i} className="h-[61px] w-full rounded-md" />
              ))}
            </div>
          ) : viewersError ? (
            <Empty className="border-none py-empty">
              <EmptyHeader>
                <EmptyMedia>
                  <Icon
                    icon="fa-solid fa-triangle-exclamation"
                    wrapperClassName="size-20 opacity-25"
                    className="text-[5rem]"
                  />
                </EmptyMedia>
                <EmptyTitle>載入觀眾資料失敗</EmptyTitle>
                <EmptyDescription>請重新整理頁面，若問題持續請檢查伺服器狀態</EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : viewers.length === 0 ? (
            <Empty className="border-none py-empty">
              <EmptyHeader>
                <EmptyMedia>
                  <Icon
                    icon="fa-solid fa-users"
                    wrapperClassName="size-20 opacity-25"
                    className="text-[5rem]"
                  />
                </EmptyMedia>
                <EmptyTitle>尚無觀眾資料</EmptyTitle>
                <EmptyDescription>
                  每場直播結束後會累積觀眾資料，歷史紀錄可在此查閱
                </EmptyDescription>
              </EmptyHeader>
            </Empty>
          ) : (
            <ViewerList
              filtered={filtered}
              sort={sort}
              sortDir={sortDir}
              search={search}
              hoveredUserId={hoveredUserId}
              onSort={handleSort}
              onSelect={setSelectedUserId}
              onHover={setHoveredUserId}
            />
          )}
        </div>
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
