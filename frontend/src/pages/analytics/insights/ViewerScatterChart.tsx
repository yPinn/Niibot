import React, { useCallback, useState } from 'react'
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

import { type ChannelBadges, type ViewerSummary } from '@/api/analytics'
import { Icon, TwitchBadgeGroup } from '@/components/primitives'
import { Switch, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import { buildViewerBadges, formatCompact } from './utils'

const AXIS_MAX = 999_999
const SCATTER_TOOLTIP_THRESHOLD = 60

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
        <p className="text-label text-muted-foreground">
          Cheer {d.total_bits.toLocaleString()} 小奇點
        </p>
      )}
      {d.total_gifts > 0 && (
        <p className="text-label text-muted-foreground">贈禮 {d.total_gifts.toLocaleString()} 份</p>
      )}
    </div>
  )
}

const QUADRANTS = [
  { color: 'var(--status-success)', label: '核心粉絲', desc: '高觀看・高互動' },
  { color: 'var(--chart-4)', label: '留言常客', desc: '低觀看・高互動' },
  { color: 'var(--chart-2)', label: '靜默觀看', desc: '高觀看・低互動' },
  { color: 'var(--muted-foreground)', label: '偶爾過路', desc: '低觀看・低互動' },
]

function computePearson(data: DotData[]): number | null {
  if (data.length < 3) return null
  const n = data.length
  const meanX = data.reduce((s, d) => s + d.x, 0) / n
  const meanY = data.reduce((s, d) => s + d.y, 0) / n
  let num = 0,
    denX = 0,
    denY = 0
  for (const d of data) {
    const dx = d.x - meanX
    const dy = d.y - meanY
    num += dx * dy
    denX += dx * dx
    denY += dy * dy
  }
  if (denX === 0 || denY === 0) return null
  return num / Math.sqrt(denX * denY)
}

function pearsonLabel(r: number): string {
  const abs = Math.abs(r)
  const dir = r >= 0 ? '正' : '負'
  if (abs >= 0.7) return `強${dir}相關`
  if (abs >= 0.4) return `中度${dir}相關`
  if (abs >= 0.1) return `弱${dir}相關`
  return '無明顯相關'
}

export function ViewerScatterChart({
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
  const [logScale, setLogScale] = useState(false)

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

  // Clamp zeros to 1 in log scale so points don't vanish
  const plotData = React.useMemo(
    () => (logScale ? data.map(d => ({ ...d, x: Math.max(1, d.x), y: Math.max(1, d.y) })) : data),
    [data, logScale]
  )

  const { midX, midY } = React.useMemo(() => {
    if (plotData.length < 2) return { midX: 0, midY: 0 }
    const xs = [...plotData].map(d => d.x).sort((a, b) => a - b)
    const ys = [...plotData].map(d => d.y).sort((a, b) => a - b)
    return {
      midX: xs[Math.floor(xs.length / 2)],
      midY: ys[Math.floor(ys.length / 2)],
    }
  }, [plotData])

  const pearsonR = React.useMemo(() => computePearson(data), [data])

  // Highlight top-3 by score + most extreme lurker + most extreme over-chatter
  const outlierIds = React.useMemo(() => {
    if (data.length < 5) return new Set<string>()
    const ids = new Set<string>()
    ;[...data]
      .sort((a, b) => b.score - a.score)
      .slice(0, 3)
      .forEach(d => ids.add(d.user_id))
    const withRate = data.filter(d => d.x > 0).map(d => ({ ...d, rate: d.y / d.x }))
    const topLurker = [...withRate].filter(d => d.x >= midX).sort((a, b) => a.rate - b.rate)[0]
    const topChatter = [...withRate].filter(d => d.x < midX).sort((a, b) => b.rate - a.rate)[0]
    if (topLurker) ids.add(topLurker.user_id)
    if (topChatter) ids.add(topChatter.user_id)
    return ids
  }, [data, midX])

  const shape = useCallback(
    ({ cx, cy, payload }: { cx?: number; cy?: number; payload?: DotData }) => {
      if (cx == null || cy == null || !payload) return null
      const isHovered = hoveredUserId != null && payload.user_id === hoveredUserId
      const isDimmed = hoveredUserId != null && payload.user_id !== hoveredUserId
      const isOutlier = outlierIds.has(payload.user_id)
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
      const r = isHovered ? 9 : isOutlier ? 7 : 6

      return (
        <g>
          {isOutlier && !isDimmed && (
            <circle
              cx={cx}
              cy={cy}
              r={r + 4}
              fill="none"
              stroke={fill}
              strokeWidth={1.5}
              strokeDasharray="3 2"
              opacity={0.55}
            />
          )}
          <circle
            cx={cx}
            cy={cy}
            r={r}
            style={{
              fill,
              opacity: isDimmed ? 0.15 : baseOpacity,
              transition: `opacity var(--duration-fast) var(--ease-default)`,
            }}
          />
          {isOutlier && !isDimmed && (
            <text
              x={cx}
              y={cy - r - 7}
              textAnchor="middle"
              style={{
                fontSize: 'var(--text-label)',
                fill: 'var(--muted-foreground)',
                pointerEvents: 'none',
              }}
            >
              {payload.name}
            </text>
          )}
        </g>
      )
    },
    [hoveredUserId, colorMode, outlierIds]
  )

  const axisMin = logScale ? 1 : 0

  return (
    <div className="flex flex-col gap-element h-full">
      <div className="flex items-center justify-between shrink-0">
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
        <div className="flex items-center gap-3">
          <TooltipProvider delayDuration={200}>
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => setLogScale(s => !s)}
                  className={cn(
                    'text-label px-2 py-0.5 rounded border font-mono transition-colors',
                    logScale
                      ? 'border-primary/40 text-primary bg-primary/10'
                      : 'border-transparent text-muted-foreground/40 hover:text-muted-foreground hover:border-border'
                  )}
                >
                  log
                </button>
              </TooltipTrigger>
              <TooltipContent>切換對數縮放，適合分佈差距懸殊的資料</TooltipContent>
            </Tooltip>
          </TooltipProvider>
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
      </div>
      <p className="text-label text-muted-foreground/60 shrink-0">觀看時長 × 留言數</p>
      <div className="flex-1 min-h-0">
        <ResponsiveContainer width="100%" height="100%">
          <ScatterChart
            margin={{ top: 16, right: 8, bottom: 8, left: 4 }}
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
              scale={logScale ? 'log' : 'auto'}
              domain={[axisMin, 'auto']}
              tick={({ x, y, payload }: AxisTick) => (
                <text
                  x={x}
                  y={Number(y) + 10}
                  textAnchor="middle"
                  style={{ fontSize: 'var(--text-label)' }}
                  fill="var(--muted-foreground)"
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
              scale={logScale ? 'log' : 'auto'}
              domain={[axisMin, 'auto']}
              tick={({ x, y, payload }: AxisTick) => (
                <text
                  x={Number(x) - 2}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  style={{ fontSize: 'var(--text-label)' }}
                  fill="var(--muted-foreground)"
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
                <ReferenceArea
                  x1={axisMin}
                  x2={midX}
                  y1={axisMin}
                  y2={midY}
                  fill="var(--muted-foreground)"
                  fillOpacity={0.06}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  x1={axisMin}
                  x2={midX}
                  y1={midY}
                  y2={AXIS_MAX}
                  fill="var(--chart-4)"
                  fillOpacity={0.12}
                  ifOverflow="hidden"
                />
                <ReferenceArea
                  x1={midX}
                  x2={AXIS_MAX}
                  y1={axisMin}
                  y2={midY}
                  fill="var(--chart-2)"
                  fillOpacity={0.12}
                  ifOverflow="hidden"
                />
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
            {viewers.length < SCATTER_TOOLTIP_THRESHOLD && (
              <RechartsTooltip
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                content={(props: any) => (
                  <ScatterTooltip {...props} channelBadges={channelBadges} />
                )}
                cursor={{ strokeDasharray: '3 3', stroke: 'var(--muted-foreground)' }}
              />
            )}
            <Scatter data={plotData} shape={shape} />
          </ScatterChart>
        </ResponsiveContainer>
      </div>
      <div className="flex items-center justify-between shrink-0">
        <div className="flex-1">
          {pearsonR !== null && (
            <TooltipProvider delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>
                  <div className="flex items-center gap-1 cursor-default select-none">
                    <span className="text-label text-muted-foreground/40">r =</span>
                    <span className="text-label font-medium tabular-nums text-muted-foreground">
                      {pearsonR.toFixed(2)}
                    </span>
                  </div>
                </TooltipTrigger>
                <TooltipContent side="top" align="start">
                  {pearsonLabel(pearsonR)}：觀看時長與留言數的線性相關程度
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )}
        </div>
        {colorMode === 'score' ? (
          <div className="flex items-center gap-2">
            <span className="text-label text-muted-foreground/50">低活躍</span>
            <div className="flex items-center gap-1">
              <div className="w-2.5 h-2.5 rounded-full bg-muted-foreground opacity-50" />
              <div className="w-2.5 h-2.5 rounded-full bg-chart-5" />
              <div className="w-2.5 h-2.5 rounded-full bg-chart-3" />
            </div>
            <span className="text-label text-muted-foreground/50">高活躍</span>
          </div>
        ) : (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-muted-foreground opacity-50" />
              <span className="text-label text-muted-foreground/50">未訂閱</span>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-full bg-status-special" />
              <span className="text-label text-muted-foreground/50">訂閱中</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
