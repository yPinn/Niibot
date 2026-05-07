import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react'
import {
  CartesianGrid,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  type ChannelBadges,
  type ChannelInsights,
  getChannelBadges,
  getInsights,
  getViewerProfile,
  listViewers,
  syncChannelRoles,
  type ViewerProfile,
  type ViewerSessionAttendance,
  type ViewerSummary,
} from '@/api/analytics'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  type BadgeEntry,
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
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
  TwitchBadgeGroup,
  type TwitchRole,
  TwitchRoleBadge,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { cn } from '@/lib/utils'

// Descending — find() returns first tier ≤ total
const BITS_TIERS = [
  5000000, 4500000, 4000000, 3500000, 3000000, 2500000, 2000000, 1750000, 1500000, 1250000, 1000000,
  900000, 800000, 700000, 600000, 500000, 400000, 300000, 200000, 100000, 75000, 50000, 25000,
  10000, 5000, 1000, 100, 1,
]
const SUB_GIFTER_TIERS = [
  5000, 4000, 3000, 2000, 1000, 950, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350,
  300, 250, 200, 150, 100, 50, 25, 10, 5, 1,
]
function getBitsTier(n: number): string | null {
  if (n <= 0) return null
  const t = BITS_TIERS.find(v => n >= v)
  return t != null ? String(t) : null
}
function getSubGifterTier(n: number): string | null {
  if (n <= 0) return null
  const t = SUB_GIFTER_TIERS.find(v => n >= v)
  return t != null ? String(t) : null
}
function subGifterBadge(totalGifts: number): { role: TwitchRole; version: string }[] {
  const tier = getSubGifterTier(totalGifts)
  return tier ? [{ role: 'sub_gifter' as TwitchRole, version: tier }] : []
}
function bitsBadge(
  totalBits: number,
  bits?: ChannelBadges['sets']['bits'] | null
): { role: TwitchRole; version: string; src: string | null }[] {
  const tier = getBitsTier(totalBits)
  if (!tier) return []
  const src = bits?.find(v => v.id === tier)?.image_url_1x ?? null
  return [{ role: 'bits' as TwitchRole, version: tier, src }]
}

const AXIS_MAX = 999_999

type BadgeSource = Pick<
  ViewerSummary,
  'is_mod' | 'is_vip' | 'is_subscribed' | 'total_gifts' | 'total_bits'
>

function buildViewerBadges(v: BadgeSource, channelBadges: ChannelBadges | null): BadgeEntry[] {
  return [
    ...(v.is_mod ? [{ role: 'moderator' as TwitchRole }] : []),
    ...(v.is_vip ? [{ role: 'vip' as TwitchRole }] : []),
    ...(v.is_subscribed
      ? [{ role: 'subscriber' as TwitchRole, src: channelBadges?.subscriber_1m ?? undefined }]
      : []),
    ...subGifterBadge(v.total_gifts),
    ...bitsBadge(v.total_bits, channelBadges?.sets?.bits),
  ]
}

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
    gradient: 'bg-gradient-to-r from-rank-gold/15',
    border: 'border-rank-gold/30',
    icon: 'fa-solid fa-trophy',
    color: 'text-rank-gold',
  },
  2: {
    gradient: 'bg-gradient-to-r from-rank-silver/15',
    border: 'border-rank-silver/30',
    icon: 'fa-solid fa-medal',
    color: 'text-rank-silver',
  },
  3: {
    gradient: 'bg-gradient-to-r from-rank-bronze/15',
    border: 'border-rank-bronze/30',
    icon: 'fa-solid fa-medal',
    color: 'text-rank-bronze',
  },
} as const

interface ViewerRowProps {
  viewer: ViewerSummary
  rank: number
  isHovered: boolean
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
  channelBadges: ChannelBadges | null
}

const ViewerRow = React.memo(function ViewerRow({
  viewer,
  rank,
  isHovered,
  onSelect,
  onHover,
  channelBadges,
}: ViewerRowProps) {
  const name = viewer.display_name || viewer.username
  const top = rank <= 3 ? RANK_STYLES[rank as 1 | 2 | 3] : null
  return (
    <button
      onClick={() => onSelect(viewer.user_id)}
      onMouseEnter={() => onHover(viewer.user_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        'w-full grid items-center gap-3 rounded-md border px-3 py-2 hover:bg-accent transition-colors text-left',
        ROW_GRID,
        top && `${top.gradient} ${top.border}`,
        isHovered && 'ring-1 ring-inset ring-primary/40'
      )}
    >
      {top ? (
        <span className={`flex justify-center ${top.color}`}>
          <i className={`${top.icon} text-xs`} />
        </span>
      ) : (
        <span className="text-sub font-mono font-semibold text-muted-foreground text-right">
          {rank}
        </span>
      )}
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <TwitchBadgeGroup badges={buildViewerBadges(viewer, channelBadges)} />
          <p className="text-content font-medium truncate">{name}</p>
        </div>
        <p className="text-label text-muted-foreground truncate">@{viewer.username}</p>
      </div>
      <Col value={viewer.total_messages.toLocaleString()} />
      <Col value={formatDuration(viewer.watch_seconds)} />
      <Col value={viewer.engagement_score.toFixed(1)} valueClassName="text-primary" />
    </button>
  )
})

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
  rankMap: Map<string, number>
  sort: SortKey
  sortDir: 'desc' | 'asc'
  search: string
  hoveredUserId: string | null
  channelBadges: ChannelBadges | null
  onSort: (key: SortKey) => void
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
}

function ViewerList({
  filtered,
  rankMap,
  sort,
  sortDir,
  search,
  hoveredUserId,
  channelBadges,
  onSort,
  onSelect,
  onHover,
}: ViewerListProps) {
  if (filtered.length === 0) {
    return (
      <Empty className="border-none py-empty lg:flex-1">
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
    <div className="flex flex-col flex-1 min-h-0">
      <div
        className={`grid items-center gap-3 px-3 py-3 border border-transparent text-label text-muted-foreground shrink-0 ${ROW_GRID}`}
      >
        <span />
        <span>觀眾</span>
        {SORT_COLS.map(col => {
          const active = sort === col.key
          const btn = (
            <button
              type="button"
              onClick={() => onSort(col.key)}
              aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
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
          if (col.key !== 'score') return <React.Fragment key={col.key}>{btn}</React.Fragment>
          return (
            <TooltipProvider key={col.key} delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>{btn}</TooltipTrigger>
                <TooltipContent className="max-w-52 text-center">
                  觀看時長＋留言活躍度＋訂閱／小奇點加成，連續出席享乘數加成
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )
        })}
      </div>
      <div className="flex flex-col gap-1 overflow-y-auto flex-1 min-h-0 scrollbar">
        {filtered.map((v, i) => {
          const rank = rankMap.get(v.user_id) ?? filtered.length + 1
          const showLowDivider =
            sort === 'score' &&
            sortDir === 'desc' &&
            v.engagement_score < 10 &&
            (i === 0 || filtered[i - 1].engagement_score >= 10)
          return (
            <React.Fragment key={v.user_id}>
              {showLowDivider && (
                <div className="flex items-center gap-2 px-1 py-1.5">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-label text-muted-foreground/50 shrink-0">低活躍</span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}
              <ViewerRow
                viewer={v}
                rank={rank}
                isHovered={hoveredUserId === v.user_id}
                onSelect={onSelect}
                onHover={onHover}
                channelBadges={channelBadges}
              />
            </React.Fragment>
          )
        })}
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
  is_subscribed: boolean
  is_mod: boolean
  is_vip: boolean
  total_bits: number
  total_gifts: number
}
type AxisTick = { x: string | number; y: string | number; payload: { value: number } }

function ScatterTooltip({
  active,
  payload,
  channelBadges,
}: {
  active?: boolean
  payload?: { payload: DotData }[]
  channelBadges: ChannelBadges | null
}) {
  if (!active || !payload?.length) return null
  const d = payload[0]?.payload
  if (!d) return null
  const mins = d.x
  const watchLabel = mins >= 60 ? `${Math.floor(mins / 60)}h ${mins % 60}m` : `${mins}m`

  const badges = buildViewerBadges(d, channelBadges)

  return (
    <div className="rounded-md border bg-popover px-3 py-2 text-popover-foreground shadow-sm space-y-1">
      <div className="flex items-center gap-1.5">
        {badges.length > 0 && <TwitchBadgeGroup badges={badges} />}
        <p className="text-sub font-medium">{d.name}</p>
      </div>
      <p className="text-label text-muted-foreground">
        留言 {d.y.toLocaleString()} · {watchLabel}
      </p>
      <p className="text-label text-primary">活躍度 {d.score.toFixed(1)}</p>
      {d.total_bits > 0 && (
        <p className="text-label text-muted-foreground">Cheer {d.total_bits.toLocaleString()}</p>
      )}
      {d.total_gifts > 0 && (
        <p className="text-label text-muted-foreground">贈禮 {d.total_gifts.toLocaleString()} 份</p>
      )}
    </div>
  )
}

function ViewerScatterChart({
  viewers,
  hoveredUserId,
  onHover,
  channelBadges,
}: {
  viewers: ViewerSummary[]
  hoveredUserId: string | null
  onHover: (id: string | null) => void
  channelBadges: ChannelBadges | null
}) {
  const [colorMode, setColorMode] = useState<'score' | 'sub'>('score')

  const data = React.useMemo(
    () =>
      viewers.map(v => ({
        x: Math.round(v.watch_seconds / 60),
        y: v.total_messages,
        score: v.engagement_score,
        name: v.display_name || v.username,
        user_id: v.user_id,
        is_subscribed: v.is_subscribed,
        is_mod: v.is_mod,
        is_vip: v.is_vip,
        total_bits: v.total_bits,
        total_gifts: v.total_gifts,
      })),
    [viewers]
  )

  const { midX, midY } = React.useMemo(() => {
    if (data.length < 2) return { midX: 0, midY: 0 }
    const xs = [...data].map(d => d.x).sort((a, b) => a - b)
    const ys = [...data].map(d => d.y).sort((a, b) => a - b)
    return {
      midX: xs[Math.floor(xs.length / 2)],
      midY: ys[Math.floor(ys.length / 2)],
    }
  }, [data])

  const shape = useCallback(
    ({ cx, cy, payload }: { cx?: number; cy?: number; payload?: DotData }) => {
      if (cx == null || cy == null || !payload) return null
      const isHovered = hoveredUserId != null && payload.user_id === hoveredUserId
      const isDimmed = hoveredUserId != null && payload.user_id !== hoveredUserId
      const fill =
        colorMode === 'sub'
          ? payload.is_subscribed
            ? 'var(--status-special)'
            : 'var(--muted-foreground)'
          : payload.score >= 25
            ? 'var(--chart-3)'
            : payload.score >= 8
              ? 'var(--chart-5)'
              : 'var(--muted-foreground)'
      const baseOpacity = colorMode === 'score' && payload.score < 8 ? 0.5 : 1
      return (
        <circle
          cx={cx}
          cy={cy}
          r={isHovered ? 9 : 6}
          style={{
            fill,
            opacity: isDimmed ? 0.15 : baseOpacity,
            transition: 'opacity 0.15s ease',
          }}
        />
      )
    },
    [hoveredUserId, colorMode]
  )

  const QUADRANTS = [
    { color: 'var(--status-success)', label: '核心粉絲', desc: '高觀看・高互動' },
    { color: 'var(--chart-4)', label: '留言常客', desc: '低觀看・高互動' },
    { color: 'var(--chart-2)', label: '靜默觀看', desc: '高觀看・低互動' },
    { color: 'var(--muted-foreground)', label: '偶爾過路', desc: '低觀看・低互動' },
  ]

  return (
    <div className="flex flex-col gap-element">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <p className="text-label text-muted-foreground">觀眾分佈</p>
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button type="button" className="flex items-center">
                  <Icon
                    icon="fa-regular fa-circle-question"
                    size="xs"
                    wrapperClassName="text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors"
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right" className="p-2.5">
                <div className="grid grid-cols-[auto_auto_1fr] items-center gap-x-2 gap-y-1.5">
                  {QUADRANTS.map(q => (
                    <React.Fragment key={q.label}>
                      <div
                        className="w-2.5 h-2.5 rounded-sm shrink-0"
                        style={{ background: q.color, opacity: 0.8 }}
                      />
                      <span className="font-medium text-label whitespace-nowrap">{q.label}</span>
                      <span className="text-label text-muted-foreground whitespace-nowrap">
                        · {q.desc}
                      </span>
                    </React.Fragment>
                  ))}
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className={cn(
              'text-label transition-colors',
              colorMode === 'score' ? 'text-foreground' : 'text-muted-foreground/50'
            )}
          >
            活躍度
          </span>
          <Switch
            checked={colorMode === 'sub'}
            onCheckedChange={checked => setColorMode(checked ? 'sub' : 'score')}
          />
          <span
            className={cn(
              'text-label transition-colors',
              colorMode === 'sub' ? 'text-foreground' : 'text-muted-foreground/50'
            )}
          >
            訂閱
          </span>
        </div>
      </div>
      <p className="text-label text-muted-foreground/60">觀看時長 × 留言數</p>
      <ResponsiveContainer width="100%" height={320}>
        <ScatterChart
          margin={{ top: 4, right: 8, bottom: 8, left: 4 }}
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          onMouseMove={(state: any) => {
            const point = state?.activePayload?.[0]?.payload as DotData | undefined
            onHover(point?.user_id ?? null)
          }}
          onMouseLeave={() => onHover(null)}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="x"
            type="number"
            domain={[0, 'auto']}
            tick={({ x, y, payload }: AxisTick) => (
              <text
                x={x}
                y={Number(y) + 10}
                textAnchor="middle"
                className="fill-muted-foreground text-label"
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
                style={{ fontSize: 11 }}
              >
                {formatCompact(payload.value)}
              </text>
            )}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          {midX > 0 && midY > 0 && (
            <>
              {/* 底左：偶爾過路 */}
              <ReferenceArea
                x1={0}
                x2={midX}
                y1={0}
                y2={midY}
                fill="var(--muted-foreground)"
                fillOpacity={0.06}
                ifOverflow="hidden"
              />
              {/* 頂左：留言常客 */}
              <ReferenceArea
                x1={0}
                x2={midX}
                y1={midY}
                y2={AXIS_MAX}
                fill="var(--chart-4)"
                fillOpacity={0.12}
                ifOverflow="hidden"
              />
              {/* 底右：靜默觀看 */}
              <ReferenceArea
                x1={midX}
                x2={AXIS_MAX}
                y1={0}
                y2={midY}
                fill="var(--chart-2)"
                fillOpacity={0.12}
                ifOverflow="hidden"
              />
              {/* 頂右：核心粉絲 */}
              <ReferenceArea
                x1={midX}
                x2={AXIS_MAX}
                y1={midY}
                y2={AXIS_MAX}
                fill="var(--status-success)"
                fillOpacity={0.1}
                ifOverflow="hidden"
              />
              <ReferenceLine
                x={midX}
                stroke="var(--border)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                ifOverflow="hidden"
              />
              <ReferenceLine
                y={midY}
                stroke="var(--border)"
                strokeWidth={1.5}
                strokeDasharray="4 3"
                ifOverflow="hidden"
              />
            </>
          )}
          <RechartsTooltip
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            content={(props: any) => <ScatterTooltip {...props} channelBadges={channelBadges} />}
            cursor={{ strokeDasharray: '3 3', stroke: 'var(--muted-foreground)' }}
          />
          <Scatter data={data} shape={shape} />
        </ScatterChart>
      </ResponsiveContainer>
      {colorMode === 'score' ? (
        <div className="flex items-center gap-2 self-end">
          <span className="text-label text-muted-foreground/50">低活躍</span>
          <div className="flex items-center gap-1">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: 'var(--muted-foreground)', opacity: 0.5 }}
            />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--chart-5)' }} />
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: 'var(--chart-3)' }} />
          </div>
          <span className="text-label text-muted-foreground/50">高活躍</span>
        </div>
      ) : (
        <div className="flex items-center gap-3 self-end">
          <div className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: 'var(--muted-foreground)', opacity: 0.5 }}
            />
            <span className="text-label text-muted-foreground/50">未訂閱</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div
              className="w-2.5 h-2.5 rounded-full"
              style={{ background: 'var(--status-special)' }}
            />
            <span className="text-label text-muted-foreground/50">訂閱中</span>
          </div>
        </div>
      )}
    </div>
  )
}

// ─── Viewer Heatmap ───────────────────────────────────────────────────────────

type HeatmapFields = Pick<
  ViewerSessionAttendance,
  'attended' | 'stream_duration_seconds' | 'viewer_watch_seconds'
>

function watchPercent(s: HeatmapFields): number {
  if (!s.attended || !s.stream_duration_seconds || !s.viewer_watch_seconds) return 0
  return Math.min(100, Math.round((s.viewer_watch_seconds / s.stream_duration_seconds) * 100))
}

function heatmapOpacity(attended: boolean, pct: number): number {
  if (!attended) return 0.2
  if (pct === 0) return 0.25
  if (pct <= 25) return 0.42
  if (pct <= 50) return 0.6
  if (pct <= 75) return 0.8
  return 1
}

const COLS = 10

const LEGEND_DOTS: HeatmapFields[] = [
  { attended: false, stream_duration_seconds: 0, viewer_watch_seconds: 0 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 0 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 30 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 60 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 100 },
]

function HeatmapCell({ s }: { s: ViewerSessionAttendance }) {
  const pct = watchPercent(s)
  const watchLabel = formatDuration(s.viewer_watch_seconds)
  const dateLabel = formatDate(s.started_at)
  const ariaLabel = !s.attended
    ? `${dateLabel} 未出席`
    : pct > 0
      ? `${dateLabel} 觀看 ${watchLabel} (${pct}%)`
      : `${dateLabel} 出席`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          role="img"
          aria-label={ariaLabel}
          className="rounded-sm cursor-default hover:scale-125 transition-transform"
          style={{
            aspectRatio: '1',
            background: s.attended ? 'var(--primary)' : 'var(--muted-foreground)',
            opacity: heatmapOpacity(s.attended, pct),
          }}
        />
      </TooltipTrigger>
      <TooltipContent side="top">
        <p className="text-sub font-medium">{dateLabel}</p>
        {!s.attended ? (
          <p className="text-label opacity-70">未出席</p>
        ) : pct > 0 ? (
          <p className="text-label opacity-70">
            觀看 {watchLabel}
            <span className="ml-1 text-primary">({pct}%)</span>
          </p>
        ) : (
          <p className="text-label opacity-70">出席（無觀看紀錄）</p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

function ViewerHeatmap({
  sessions,
  streakCount,
}: {
  sessions: ViewerSessionAttendance[]
  streakCount?: number
}) {
  const attended = React.useMemo(() => sessions.filter(s => s.attended).length, [sessions])

  if (sessions.length === 0) return null

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <p className="text-label text-muted-foreground">出席紀錄</p>
          <div className="flex items-center gap-2">
            {streakCount != null && streakCount > 1 && (
              <Badge
                variant="outline"
                className="rounded-sm text-primary border-primary/30 bg-primary/5 font-normal"
              >
                <i className="fa-solid fa-fire" />
                連續 {streakCount} 場
              </Badge>
            )}
            <p className="text-label text-muted-foreground/60">
              {attended} / {sessions.length} 場
            </p>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${COLS}, 1fr)`,
            gap: 3,
          }}
        >
          {sessions.map(s => (
            <HeatmapCell key={s.session_id} s={s} />
          ))}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-2 self-end">
          <span className="text-label text-muted-foreground/50">未出席</span>
          <div className="flex gap-0.5">
            {LEGEND_DOTS.map((d, i) => (
              <div
                key={i}
                className="w-2.5 h-2.5 rounded-sm"
                style={{
                  background: d.attended ? 'var(--primary)' : 'var(--muted-foreground)',
                  opacity: heatmapOpacity(d.attended, watchPercent(d)),
                }}
              />
            ))}
          </div>
          <span className="text-label text-muted-foreground/50">100%</span>
        </div>
      </div>
    </TooltipProvider>
  )
}

// ─── Viewer Sheet ─────────────────────────────────────────────────────────────

const EVENT_META: Record<string, { icon: string; label: string; color: string }> = {
  follow: { icon: 'fa-solid fa-heart', label: '追隨', color: 'text-status-follow' },
  subscribe: { icon: 'fa-solid fa-star', label: '訂閱', color: 'text-status-special' },
  cheer: { icon: 'fa-solid fa-diamond-half-stroke', label: '小奇點', color: 'text-primary' },
  raid: { icon: 'fa-solid fa-parachute-box', label: '揪團', color: 'text-status-info' },
}

const SUB_TIER_LABEL: Record<string, string> = {
  '1': '層級 1',
  T1: '層級 1',
  '2': '層級 2',
  T2: '層級 2',
  '3': '層級 3',
  T3: '層級 3',
}

interface ViewerSheetProps {
  userId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  days: number
  channelBadges: ChannelBadges | null
}

function ProfileAvatar({
  src,
  name,
  size,
}: {
  src?: string | null
  name: string
  size: 'lg' | 'sm'
}) {
  const cls = size === 'lg' ? 'h-16 w-16 ring-2 ring-background' : 'h-11 w-11 shrink-0'
  return src ? (
    <img src={src} alt={name} className={`${cls} rounded-full object-cover`} />
  ) : (
    <div
      className={`${cls} rounded-full bg-muted flex items-center justify-center text-sub font-bold text-muted-foreground select-none`}
    >
      {name.charAt(0).toUpperCase()}
    </div>
  )
}

function UsernameLink({ username }: { username: string | undefined }) {
  if (!username) return <span>觀眾資料</span>
  return (
    <a
      href={`https://twitch.tv/${username}`}
      target="_blank"
      rel="noopener noreferrer"
      className="select-text hover:text-foreground hover:underline transition-colors"
    >
      @{username}
    </a>
  )
}

function PartnerBadge() {
  return (
    <TooltipProvider delayDuration={200}>
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
  role,
  badgeSrc,
  iconClass,
  children,
}: {
  icon?: string
  role?: TwitchRole
  badgeSrc?: string | null
  iconClass?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3">
      {role ? (
        <TwitchRoleBadge role={role} src={badgeSrc ?? null} size={18} />
      ) : (
        <Icon icon={icon!} size="badge" wrapperClassName={cn('shrink-0', iconClass)} />
      )}
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
          <Badge
            variant="outline"
            className="rounded-sm text-muted-foreground tabular-nums font-normal"
          >
            {badge}
          </Badge>
        )}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-card-title font-bold tabular-nums leading-none">{value}</p>
        <Icon icon={icon} size="sm" wrapperClassName="text-primary/70" />
      </div>
    </div>
  )

  if (!tooltip) return inner

  return (
    <TooltipProvider delayDuration={200}>
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

function ViewerSheet({ userId, open, onOpenChange, days, channelBadges }: ViewerSheetProps) {
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
  const totalGifts = profile?.total_gifts ?? 0

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
              <div className="absolute inset-x-0 bottom-0 h-3/4 bg-linear-to-t from-background via-background/50 to-transparent" />
            </div>
            <div className="relative z-10 flex items-end gap-3 px-page pb-3 pr-12 -mt-8">
              <div className="shrink-0 relative z-10">
                <ProfileAvatar src={profile.profile_image_url} name={name} size="lg" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-content font-semibold leading-snug truncate select-text">
                    {name}
                  </span>
                  {isPartner && <PartnerBadge />}
                </div>
                <p className="text-label text-muted-foreground mt-0.5">
                  <UsernameLink username={username} />
                </p>
              </div>
            </div>
          </div>
        ) : (
          /* ── No banner mode ── */
          <SheetHeader className="pr-10 shrink-0">
            <div className="flex items-center gap-3">
              <ProfileAvatar src={profile?.profile_image_url} name={name} size="sm" />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <SheetTitle className="text-content leading-snug select-text">{name}</SheetTitle>
                  {isPartner && <PartnerBadge />}
                </div>
                <SheetDescription className="text-label mt-0.5">
                  <UsernameLink username={username} />
                </SheetDescription>
              </div>
            </div>
          </SheetHeader>
        )}

        {loading ? (
          <>
            <SheetSection className="space-y-3">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-40" />
            </SheetSection>
            <SheetSection>
              <div className="flex flex-col gap-2">
                <div className="flex justify-between">
                  <Skeleton className="h-3.5 w-16" />
                  <Skeleton className="h-3.5 w-12" />
                </div>
                <div
                  style={{ display: 'grid', gridTemplateColumns: `repeat(${COLS}, 1fr)`, gap: 3 }}
                >
                  {Array.from({ length: 20 }).map((_, i) => (
                    <Skeleton key={i} className="rounded-sm" style={{ aspectRatio: '1' }} />
                  ))}
                </div>
              </div>
            </SheetSection>
            <SheetSection>
              <div className="grid grid-cols-2 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-[73px] rounded-md" />
                ))}
              </div>
            </SheetSection>
            <SheetSection className="flex-1">
              <div className="space-y-1.5">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-9 rounded-md" />
                ))}
              </div>
            </SheetSection>
          </>
        ) : profile ? (
          <>
            {/* Follow / Sub / Role / Ban status */}
            <SheetSection className="space-y-3">
              <StatusRow icon="fa-solid fa-heart" iconClass="text-status-follow">
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
                <StatusRow
                  role={channelBadges?.subscriber_1m ? 'subscriber' : undefined}
                  badgeSrc={channelBadges?.subscriber_1m ?? null}
                  icon="fa-solid fa-star"
                  iconClass="text-status-special"
                >
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
                <StatusRow role="moderator">
                  <span className="font-medium">頻道管理員</span>
                </StatusRow>
              )}
              {twitch?.is_vip && (
                <StatusRow role="vip">
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

            {/* Attendance heatmap */}
            {profile.session_attendance.length > 0 && (
              <SheetSection>
                <ViewerHeatmap
                  sessions={profile.session_attendance}
                  streakCount={profile.streak_count}
                />
              </SheetSection>
            )}

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
                  icon="fa-solid fa-gift"
                  value={totalGifts > 0 ? totalGifts.toLocaleString() : '—'}
                  label="贈禮訂閱"
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
              <div className="flex flex-col gap-y-1 mt-3">
                <p className="text-label text-muted-foreground">
                  最後活躍：{formatDateFull(profile.last_seen)}
                </p>
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
                        key={`${i}-${ev.occurred_at}-${ev.event_type}`}
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
  const [sheetOpen, setSheetOpen] = useState(false)
  const [hoveredUserId, setHoveredUserId] = useState<string | null>(null)
  const [channelBadges, setChannelBadges] = useState<ChannelBadges | null>(null)
  const [isSyncing, setIsSyncing] = useState(false)
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

  const handleSyncRoles = useCallback(async () => {
    if (isSyncing) return
    setIsSyncing(true)
    try {
      await syncChannelRoles()
      void fetchViewers(Number(period), true)
    } catch {
      // silent — button returns to idle state
    } finally {
      setIsSyncing(false)
    }
  }, [isSyncing, period, fetchViewers])

  const handlePeriodChange = (value: string) => {
    if (value === period) return
    loadedForRef.current = null
    setInitialized(false)
    setInsightsLoading(true)
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

  const { filtered, rankMap } = React.useMemo(() => {
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
    const rankMap = new Map(sorted.map((v, i) => [v.user_id, i + 1]))
    const q = search.trim().toLowerCase()
    const filtered = q
      ? sorted.filter(v => {
          if (q === 'mod' || q === '管理員' || q === '管理') return v.is_mod
          if (q === 'vip') return v.is_vip
          if (q === 'sub' || q === '訂閱') return v.is_subscribed
          return (
            (v.display_name ?? '').toLowerCase().includes(q) || v.username.toLowerCase().includes(q)
          )
        })
      : sorted
    return { filtered, rankMap }
  }, [viewers, search, sort, sortDir])

  return (
    <PageMain className="h-full overflow-hidden">
      {/* Header + controls */}
      <SlideUpSm inView className="flex items-end justify-between gap-element">
        <div>
          <h1 className="text-page-title font-bold">Insights</h1>
          <p className="text-sub text-muted-foreground mt-0.5">觀眾互動與活躍度數據</p>
        </div>
        <Tabs value={period} onValueChange={handlePeriodChange}>
          <TabsList>
            {PERIODS.map(p => (
              <TabsTrigger key={p.value} value={p.value}>
                {p.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </SlideUpSm>

      {/* Main 2-col layout */}
      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-2 gap-section flex-1 min-h-0 overflow-y-auto lg:overflow-hidden lg:grid-rows-1"
      >
        {/* Left: sticky – chart + summary cards */}
        <div className="rounded-lg border bg-card p-section lg:self-start flex flex-col gap-section">
          {!initialized ? (
            <Skeleton className="hidden lg:block h-[370px] rounded-md" />
          ) : viewers.length > 0 ? (
            <div className="hidden lg:block rounded-md bg-muted/20 p-3 **:outline-none">
              <ViewerScatterChart
                viewers={viewers}
                hoveredUserId={hoveredUserId}
                onHover={setHoveredUserId}
                channelBadges={channelBadges}
              />
            </div>
          ) : null}
          {(!initialized || viewers.length > 0) && <Separator className="hidden lg:block" />}
          <Stagger key={insightsLoading ? 'l' : 'd'} className="grid grid-cols-2 gap-section">
            {insightsLoading ? (
              Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-17.25 rounded-md" />
              ))
            ) : (
              <>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-tower-broadcast"
                    value={insights?.total_sessions?.toLocaleString() ?? '—'}
                    label="串流場數"
                    iconClassName="text-muted-foreground/60"
                  />
                </StaggerItem>
                <StaggerItem>
                  <SummaryTile
                    icon="fa-solid fa-hourglass-half"
                    value={
                      insights?.total_stream_seconds != null && insights.total_stream_seconds > 0
                        ? formatDuration(insights.total_stream_seconds)
                        : '—'
                    }
                    label="累計直播"
                    iconClassName="text-muted-foreground/60"
                  />
                </StaggerItem>
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
                    iconClassName="text-status-follow/80"
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

        {/* Right: viewer list */}
        <div className="rounded-lg border bg-card p-section flex flex-col gap-section lg:max-h-[calc(100svh-var(--h-topbar)-2*var(--spacing-page-lg)-var(--spacing-section)-var(--h-page-header))]">
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
                    className={cn('text-sm', isSyncing && 'animate-spin')}
                  />
                </button>
              </TooltipTrigger>
              <TooltipContent>從 Twitch 同步管理員、VIP 和訂閱者身分標籤</TooltipContent>
            </Tooltip>
            <Input
              placeholder="搜尋觀眾..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="h-10 w-44"
            />
          </div>
          {!initialized ? (
            <div className="space-y-1">
              {Array.from({ length: 10 }).map((_, i) => (
                <Skeleton key={i} className="h-14.25 w-full rounded-md" />
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
            <div className="flex-1 min-h-0 flex flex-col">
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
            </div>
          )}
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
