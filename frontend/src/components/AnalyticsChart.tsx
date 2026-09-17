import { type ReactElement, useId, useMemo, useRef, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Customized,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  type XAxisTickContentProps,
  YAxis,
  type YAxisTickContentProps,
} from 'recharts'

import { type SessionSummary } from '@/api/analytics'
import { Icon } from '@/components/primitives'
import {
  Card,
  CardContent,
  Skeleton,
  Tooltip as InfoTooltip,
  TooltipContent as InfoTooltipContent,
  TooltipTrigger as InfoTooltipTrigger,
} from '@/components/ui'

interface AnalyticsData {
  total_stream_hours: number
  total_sessions: number
  total_commands: number
  total_follows: number
  total_subs: number
  avg_session_duration: number
  recent_sessions?: SessionSummary[]
}

interface AnalyticsChartProps {
  data?: AnalyticsData | null
  loading?: boolean
  days?: number
  className?: string
}

type ChartMode = 'stream_hours' | 'follows' | 'subs' | 'commands'

interface ChartConfig {
  dataKey: string
  unit: string
  label: string
}

const EMPTY_ANALYTICS: AnalyticsData = {
  total_stream_hours: 0,
  total_sessions: 0,
  total_commands: 0,
  total_follows: 0,
  total_subs: 0,
  avg_session_duration: 0,
  recent_sessions: [],
}

const MAX_CHART_DAYS = 30

const CHART_CONFIGS: Record<ChartMode, ChartConfig> = {
  stream_hours: { dataKey: 'stream_hours', unit: '小時', label: '直播時長' },
  follows: { dataKey: 'follows', unit: '人', label: '新追隨者' },
  subs: { dataKey: 'subs', unit: '人', label: '新訂閱者' },
  commands: { dataKey: 'commands', unit: '次', label: '指令使用' },
}

const DATE_FORMATTER = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})
const TIME_FORMATTER = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
})

// Transparent rect covering the full SVG area so mouse events fire in empty zones above the chart line
const ChartBackground = ({
  width = 0,
  height = 0,
}: {
  width?: number
  height?: number
  [k: string]: unknown
}) => <rect x={0} y={0} width={width} height={height} fill="transparent" />

const CustomTick = ({ x, y, payload }: XAxisTickContentProps): ReactElement => (
  <g transform={`translate(${Number(x) || 0},${Number(y) || 0})`}>
    {payload && (
      <text
        x={0}
        y={0}
        dy={16}
        textAnchor="middle"
        style={{ fontSize: 'var(--text-label)' }}
        fill="var(--muted-foreground)"
      >
        {payload.value}
      </text>
    )}
  </g>
)

const CustomYAxisTick = ({ x, y, payload }: YAxisTickContentProps): ReactElement => (
  <g transform={`translate(${Number(x) || 0},${Number(y) || 0})`}>
    {payload && (
      <text
        x={0}
        y={0}
        dx={-8}
        dy={4}
        textAnchor="end"
        style={{ fontSize: 'var(--text-label)' }}
        fill="var(--muted-foreground)"
      >
        {payload.value}
      </text>
    )}
  </g>
)

const ChartTooltip = ({
  active,
  payload,
  chartConfig,
}: TooltipContentProps<number, string> & { chartConfig: ChartConfig }) => {
  if (!active || !payload?.length) return null

  const data = payload[0].payload as {
    date: string
    sessions: SessionSummary[]
    session_count: number
  }
  const value = payload[0].value
  const firstSession = data.sessions[0]
  if (!firstSession) return null

  return (
    <div className="bg-popover border border-border rounded-lg shadow-xl overflow-hidden w-75 max-w-[calc(100vw-2rem)] flex flex-col pointer-events-auto">
      <div className="px-3 py-2 bg-primary/10 border-b border-border shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon icon="fa-solid fa-calendar" wrapperClassName="size-3.5 text-primary" />
            <span className="text-sub font-semibold text-popover-foreground">
              {DATE_FORMATTER.format(new Date(firstSession.started_at))}
            </span>
          </div>
          <span className="text-label text-muted-foreground">{data.session_count} 場直播</span>
        </div>
      </div>

      <div className="overflow-y-auto max-h-48">
        {data.sessions.map((session, index) => {
          const gameBoxArtUrl = session.game_id
            ? `https://static-cdn.jtvnw.net/ttv-boxart/${session.game_id}-144x192.jpg`
            : null

          return (
            <div
              key={session.session_id}
              className={`flex h-24 ${index > 0 ? 'border-t border-border' : ''}`}
            >
              <div className="shrink-0 w-18 overflow-hidden">
                {gameBoxArtUrl ? (
                  <img
                    src={gameBoxArtUrl}
                    alt={session.game_name || ''}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full bg-linear-to-br from-primary/20 to-primary/5 flex items-center justify-center">
                    <Icon icon="fa-solid fa-gamepad" wrapperClassName="size-8 text-primary/50" />
                  </div>
                )}
              </div>
              <div className="flex-1 px-3 py-2 flex flex-col justify-evenly">
                <div className="font-semibold text-sub text-popover-foreground line-clamp-2 leading-tight">
                  {session.title || '未設定標題'}
                </div>
                <div className="flex items-center gap-1 text-label text-muted-foreground">
                  <Icon icon="fa-solid fa-tag" wrapperClassName="size-2.5 shrink-0" />
                  <span className="truncate">{session.game_name || '未分類'}</span>
                </div>
                <div className="flex items-center gap-1.5 text-label text-muted-foreground">
                  <Icon icon="fa-solid fa-clock" wrapperClassName="size-2.5 shrink-0" />
                  <span>
                    {TIME_FORMATTER.format(new Date(session.started_at))} ·{' '}
                    {session.duration_hours.toFixed(1)} 小時
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="px-3 py-2 bg-muted/30 border-t border-border shrink-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-label text-muted-foreground">當日{chartConfig.label}</span>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-bold text-primary tabular-nums leading-none">
              {typeof value === 'number' ? value.toFixed(1) : value}
            </span>
            <span className="text-label font-medium text-primary/70">{chartConfig.unit}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default function AnalyticsChart({
  data,
  loading = false,
  days = 30,
  className = '',
}: AnalyticsChartProps) {
  const [chartMode, setChartMode] = useState<ChartMode>('stream_hours')
  const [tooltipPos, setTooltipPos] = useState<{ x: number; y: number } | undefined>(undefined)
  const gradientId = useId()
  // Track the last active data-point index so we only re-render when the snap target changes,
  // not on every pixel of cursor movement.
  const activeIdxRef = useRef<number | undefined>(undefined)

  const analyticsData = data ?? EMPTY_ANALYTICS

  const { realChartData, chartData } = useMemo(() => {
    const sessionsByDate = new Map<string, SessionSummary[]>()

    // API returns sessions ordered DESC; reverse to chronological for grouping
    ;[...(analyticsData.recent_sessions ?? [])].reverse().forEach(session => {
      const date = new Date(session.started_at)
      const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
      if (!sessionsByDate.has(dateKey)) sessionsByDate.set(dateKey, [])
      sessionsByDate.get(dateKey)!.push(session)
    })

    const real = Array.from(sessionsByDate.entries())
      .slice(-MAX_CHART_DAYS)
      .map(([dateKey, daySessions]) => {
        // Append local midnight so the date parses in the browser's timezone,
        // not as UTC (which could shift the day by -1 for negative-offset zones).
        const date = new Date(`${dateKey}T00:00:00`)
        return {
          date: `${date.getMonth() + 1}-${String(date.getDate()).padStart(2, '0')}`,
          sessions: daySessions,
          stream_hours: daySessions.reduce((sum, s) => sum + s.duration_hours, 0),
          follows: daySessions.reduce((sum, s) => sum + s.new_follows, 0),
          subs: daySessions.reduce((sum, s) => sum + s.new_subs, 0),
          commands: daySessions.reduce((sum, s) => sum + s.total_commands, 0),
          session_count: daySessions.length,
        }
      })

    // When no data, generate last 7 days with 0 values so the chart renders a flat line
    const chart =
      real.length > 0
        ? real
        : Array.from({ length: 7 }, (_, i) => {
            const d = new Date()
            d.setDate(d.getDate() - (6 - i))
            return {
              date: `${d.getMonth() + 1}-${String(d.getDate()).padStart(2, '0')}`,
              sessions: [] as SessionSummary[],
              stream_hours: 0,
              follows: 0,
              subs: 0,
              commands: 0,
              session_count: 0,
            }
          })

    return { realChartData: real, chartData: chart }
  }, [analyticsData])

  const isEmpty = realChartData.length === 0
  const chartConfig = CHART_CONFIGS[chartMode]

  // Derive tooltip position entirely from the data point, not the cursor.
  // Recharts only uses `position` prop when BOTH x and y are provided as numbers;
  // providing only y causes it to fall back to cursor-based positioning (the jitter source).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleChartMouseMove = (s: any) => {
    if (s.activeTooltipIndex === activeIdxRef.current) return
    activeIdxRef.current = s.activeTooltipIndex

    const value = s.activePayload?.[0]?.value as number | undefined
    const yAxisEntry = Object.values(
      (s as { yAxisMap?: Record<string, unknown> }).yAxisMap ?? {}
    )[0]
    const yScale =
      yAxisEntry != null && typeof yAxisEntry === 'object' && 'scale' in yAxisEntry
        ? (yAxisEntry as { scale: (v: number) => number }).scale
        : undefined
    const off = s.offset as { top: number; height: number } | undefined
    const x = s.activeCoordinate?.x as number | undefined

    if (value !== undefined && yScale && off && x !== undefined) {
      const rawY = yScale(value)
      // Clamp to plot area bounds so the tooltip never escapes the chart
      const clampedY = Math.max(off.top, Math.min(off.top + off.height, rawY))
      setTooltipPos({ x, y: clampedY })
    } else {
      setTooltipPos(undefined)
    }
  }

  const handleChartMouseLeave = () => {
    activeIdxRef.current = undefined
    setTooltipPos(undefined)
  }

  const stats = useMemo(
    () => [
      {
        mode: 'stream_hours' as ChartMode,
        label: '總直播時數',
        value: analyticsData.total_stream_hours.toFixed(1),
        unit: '小時',
        subtitle: `${analyticsData.total_sessions} 場直播`,
        icon: 'fa-solid fa-clock',
      },
      {
        mode: 'follows' as ChartMode,
        label: '新追隨者',
        value: analyticsData.total_follows,
        unit: '',
        subtitle: `過去 ${days} 天`,
        icon: 'fa-solid fa-user-plus',
      },
      {
        mode: 'subs' as ChartMode,
        label: '新訂閱者',
        value: analyticsData.total_subs,
        unit: '',
        subtitle: `過去 ${days} 天`,
        icon: 'fa-solid fa-star',
      },
      {
        mode: 'commands' as ChartMode,
        label: '指令使用',
        value: analyticsData.total_commands,
        unit: '次',
        subtitle: `過去 ${days} 天`,
        icon: 'fa-solid fa-terminal',
      },
    ],
    [analyticsData, days]
  )

  return (
    <Card className={`flex flex-col ${className}`}>
      <CardContent className="px-card py-1 flex-1 min-h-0 flex flex-col">
        <div className="flex flex-col flex-1 min-h-0 gap-3">
          <div className="flex justify-end shrink-0 -mb-1">
            <InfoTooltip>
              <InfoTooltipTrigger asChild>
                <button
                  aria-label="直播標題說明"
                  className="flex items-center justify-center size-5 rounded-full text-muted-foreground hover:text-foreground transition-colors"
                >
                  <Icon icon="fa-solid fa-circle-question" size="sm" />
                </button>
              </InfoTooltipTrigger>
              <InfoTooltipContent side="left" className="max-w-60">
                若直播紀錄顯示「未設定標題」，請至 Twitch 創作者後台開啟{' '}
                <strong>影片存檔（VOD）</strong>。 Bot 重啟後將自動補齊歷史標題。
              </InfoTooltipContent>
            </InfoTooltip>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 sm:gap-5 shrink-0 mb-1 sm:mb-2">
            {loading
              ? Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-14 sm:h-18 rounded-lg" />
                ))
              : stats.map(stat => (
                  <button
                    key={stat.mode}
                    onClick={() => setChartMode(stat.mode)}
                    className={`rounded-lg border px-2 py-1.5 sm:px-3 sm:py-2 transition-all text-left ${
                      chartMode === stat.mode
                        ? 'bg-primary/10 border-primary shadow-sm'
                        : 'bg-muted/30 hover:bg-muted/50'
                    }`}
                  >
                    <div className="flex items-center justify-between mb-0.5 sm:mb-1">
                      <span
                        className={`text-label font-medium ${chartMode === stat.mode ? 'text-primary' : 'text-foreground/80'}`}
                      >
                        {stat.label}
                      </span>
                      <Icon
                        icon={stat.icon}
                        wrapperClassName={`size-3.5 ${chartMode === stat.mode ? 'text-primary' : 'text-muted-foreground'}`}
                      />
                    </div>
                    <div className="flex items-baseline gap-1">
                      <span
                        className={`text-sub sm:text-card-title font-bold tabular-nums ${chartMode === stat.mode ? 'text-primary' : 'text-foreground'}`}
                      >
                        {stat.value}
                      </span>
                      {stat.unit && (
                        <span className="text-label font-medium text-foreground/70">
                          {stat.unit}
                        </span>
                      )}
                    </div>
                    <div className="text-label text-muted-foreground">{stat.subtitle}</div>
                  </button>
                ))}
          </div>

          <div
            className="h-48 sm:h-64 lg:flex-1 lg:min-h-0 relative select-none **:outline-none"
            onMouseDown={e => e.preventDefault()}
          >
            {isEmpty && (
              <div className="absolute inset-0 z-raised flex items-center justify-center pointer-events-none">
                <span className="text-sm text-muted-foreground/60">尚無直播數據</span>
              </div>
            )}
            <ResponsiveContainer width="100%" height="100%" debounce={50}>
              <AreaChart
                data={chartData}
                margin={{ top: 5, right: 10, left: 0, bottom: 5 }}
                tabIndex={-1}
                className="outline-none"
                onMouseMove={handleChartMouseMove}
                onMouseLeave={handleChartMouseLeave}
              >
                <Customized component={ChartBackground} />
                <defs>
                  <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--primary)" stopOpacity={0.5} />
                    <stop offset="95%" stopColor="var(--primary)" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="date" tick={CustomTick} tickLine={false} />
                <YAxis width={35} tick={CustomYAxisTick} tickLine={false} />
                {!isEmpty && (
                  <Tooltip
                    isAnimationActive={false}
                    position={tooltipPos}
                    wrapperStyle={{
                      transition: `transform var(--duration-fast) var(--ease-default), left var(--duration-fast) var(--ease-default), top var(--duration-fast) var(--ease-default)`,
                      pointerEvents: 'none',
                    }}
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                    content={(props: any) => <ChartTooltip {...props} chartConfig={chartConfig} />}
                    cursor={{ stroke: 'var(--primary)', strokeWidth: 1, strokeDasharray: '5 5' }}
                  />
                )}
                <Area
                  type="monotone"
                  dataKey={chartConfig.dataKey}
                  stroke="var(--primary)"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill={`url(#${gradientId})`}
                  activeDot={{
                    r: 6,
                    fill: 'var(--primary)',
                    stroke: 'var(--card)',
                    strokeWidth: 2,
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
