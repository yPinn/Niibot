import { type ReactElement, type SVGProps, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  type TooltipProps,
  XAxis,
  YAxis,
} from 'recharts'
import { type NameType, type ValueType } from 'recharts/types/component/DefaultTooltipContent'

import { Card, CardContent } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'

// --- 介面定義 (Interfaces) ---

interface SessionSummary {
  session_id: number
  started_at: string
  ended_at: string | null
  duration_hours: number
  total_commands: number
  new_follows: number
  new_subs: number
  title: string | null
  game_name: string | null
  game_id: string | null
}

interface AnalyticsData {
  total_stream_hours: number
  total_sessions: number
  total_commands: number
  total_follows: number
  total_subs: number
  avg_session_duration: number
  avg_viewers?: number
  recent_sessions?: SessionSummary[]
}

interface AnalyticsChartProps {
  data?: AnalyticsData | null
  loading?: boolean
  className?: string
}

type ChartMode = 'stream_hours' | 'avg_viewers' | 'follows' | 'subs'

interface ChartConfig {
  dataKey: string
  unit: string
  label: string
}

// 修正後的 Tick 介面，繼承自 SVGProps 以符合 Recharts 要求
interface CustomTickProps extends SVGProps<SVGTextElement> {
  x?: number
  y?: number
  payload?: {
    value: string | number
    index: number
  }
}

// --- 子組件 (定義在外部以避免重新渲染與解決類型衝突) ---

const CustomTick = ({ x, y, payload }: CustomTickProps): ReactElement => (
  <g transform={`translate(${x || 0},${y || 0})`}>
    {payload && (
      <text x={0} y={0} dy={16} textAnchor="middle" fontSize="12" fill="currentColor" opacity={0.7}>
        {payload.value}
      </text>
    )}
  </g>
)

const CustomYAxisTick = ({ x, y, payload }: CustomTickProps): ReactElement => (
  <g transform={`translate(${x || 0},${y || 0})`}>
    {payload && (
      <text
        x={0}
        y={0}
        dx={-8}
        dy={4}
        textAnchor="end"
        fontSize="12"
        fill="currentColor"
        opacity={0.7}
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
}: TooltipProps<ValueType, NameType> & { chartConfig: ChartConfig }) => {
  if (!active || !payload || !payload.length) return null

  const data = payload[0].payload as {
    date: string
    sessions: SessionSummary[]
    session_count: number
  }
  const value = payload[0].value

  const firstSession = data.sessions[0]
  if (!firstSession) return null

  const sessionDate = new Date(firstSession.started_at)
  const monthNames = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ]
  const formattedDate = `${monthNames[sessionDate.getMonth()]} ${sessionDate.getDate()}, ${sessionDate.getFullYear()}`

  return (
    <div className="bg-popover border border-border rounded-lg shadow-xl overflow-hidden w-[300px] flex flex-col pointer-events-auto">
      <div className="px-3 py-2 bg-primary/10 border-b border-border flex-shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Icon icon="fa-solid fa-calendar" wrapperClassName="size-3.5 text-primary" />
            <span className="text-sm font-semibold text-popover-foreground">{formattedDate}</span>
          </div>
          <span className="text-xs text-muted-foreground">{data.session_count} 場直播</span>
        </div>
      </div>

      <div className="overflow-y-auto max-h-[192px]">
        {data.sessions.map((session, index) => {
          const sessionTime = new Date(session.started_at)
          const formattedTime = `${String(sessionTime.getHours()).padStart(2, '0')}:${String(sessionTime.getMinutes()).padStart(2, '0')}`
          const game_box_art_url = session.game_id
            ? `https://static-cdn.jtvnw.net/ttv-boxart/${session.game_id}-144x192.jpg`
            : null

          return (
            <div
              key={session.session_id}
              className={`flex h-[96px] ${index > 0 ? 'border-t border-border' : ''}`}
            >
              <div className="flex-shrink-0 w-[72px] overflow-hidden">
                {game_box_art_url ? (
                  <img
                    src={game_box_art_url}
                    alt={session.game_name || ''}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full bg-gradient-to-br from-primary/20 to-primary/5 flex items-center justify-center">
                    <Icon icon="fa-solid fa-gamepad" wrapperClassName="size-8 text-primary/50" />
                  </div>
                )}
              </div>
              <div className="flex-1 px-3 py-2 flex flex-col justify-evenly">
                <div className="font-semibold text-sm text-popover-foreground line-clamp-2 leading-tight">
                  {session.title || '未設定標題'}
                </div>
                <div className="flex items-center gap-1 text-xs text-muted-foreground">
                  <Icon icon="fa-solid fa-tag" wrapperClassName="size-2.5 flex-shrink-0" />
                  <span className="truncate">{session.game_name || '未分類'}</span>
                </div>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Icon icon="fa-solid fa-clock" wrapperClassName="size-2.5 flex-shrink-0" />
                  <span>
                    {formattedTime} · {session.duration_hours.toFixed(1)}h
                  </span>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      <div className="px-3 py-2 bg-muted/30 border-t border-border flex-shrink-0">
        <div className="flex items-baseline gap-1.5">
          <span className="text-xs text-muted-foreground">當日{chartConfig.label}</span>
          <div className="flex items-baseline gap-1">
            <span className="text-xl font-bold text-primary tabular-nums leading-none">
              {typeof value === 'number' ? value.toFixed(1) : value}
            </span>
            <span className="text-xs font-medium text-primary/70">{chartConfig.unit}</span>
          </div>
        </div>
      </div>
    </div>
  )
}

// --- 主組件 ---

export default function AnalyticsChart({
  data,
  loading = false,
  className = '',
}: AnalyticsChartProps) {
  const [chartMode, setChartMode] = useState<ChartMode>('stream_hours')

  const analyticsData = data || {
    total_stream_hours: 0,
    total_sessions: 0,
    total_commands: 0,
    total_follows: 0,
    total_subs: 0,
    avg_session_duration: 0,
    avg_viewers: 0,
    recent_sessions: [],
  }

  const sessionsByDate = new Map<string, SessionSummary[]>()
  const MAX_CHART_DATA_POINTS = 20
  const recentSessions = [...(analyticsData.recent_sessions || [])]
    .reverse()
    .slice(-MAX_CHART_DATA_POINTS)

  recentSessions.forEach(session => {
    const date = new Date(session.started_at)
    const dateKey = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
    if (!sessionsByDate.has(dateKey)) sessionsByDate.set(dateKey, [])
    sessionsByDate.get(dateKey)!.push(session)
  })

  const chartData = Array.from(sessionsByDate.entries()).map(([dateKey, daySessions]) => {
    const date = new Date(dateKey)
    return {
      date: `${date.getMonth() + 1}-${String(date.getDate()).padStart(2, '0')}`,
      sessions: daySessions,
      stream_hours: daySessions.reduce((sum, s) => sum + s.duration_hours, 0),
      avg_viewers: analyticsData.avg_viewers || 0,
      follows: daySessions.reduce((sum, s) => sum + s.new_follows, 0),
      subs: daySessions.reduce((sum, s) => sum + s.new_subs, 0),
      session_count: daySessions.length,
    }
  })

  const chartConfigs: Record<ChartMode, ChartConfig> = {
    stream_hours: { dataKey: 'stream_hours', unit: '小時', label: '直播時長' },
    avg_viewers: { dataKey: 'avg_viewers', unit: '人', label: '平均觀眾' },
    follows: { dataKey: 'follows', unit: '人', label: '新追隨者' },
    subs: { dataKey: 'subs', unit: '人', label: '新訂閱者' },
  }

  const chartConfig = chartConfigs[chartMode]

  const stats = [
    {
      mode: 'stream_hours' as ChartMode,
      label: '總直播時數',
      value: analyticsData.total_stream_hours.toFixed(1),
      unit: 'h',
      subtitle: `${analyticsData.total_sessions} 場直播`,
      icon: 'fa-solid fa-clock',
    },
    {
      mode: 'avg_viewers' as ChartMode,
      label: '平均觀眾',
      value: analyticsData.avg_viewers || 0,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-users',
    },
    {
      mode: 'follows' as ChartMode,
      label: '新追隨者',
      value: analyticsData.total_follows,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-user-plus',
    },
    {
      mode: 'subs' as ChartMode,
      label: '新訂閱者',
      value: analyticsData.total_subs,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-star',
    },
  ]

  return (
    <Card className={className}>
      <CardContent className="p-5">
        <div className="space-y-5">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {stats.map(stat => (
              <button
                key={stat.mode}
                onClick={() => setChartMode(stat.mode)}
                disabled={loading}
                className={`rounded-lg border p-3 space-y-1.5 transition-all text-left ${
                  loading
                    ? 'opacity-60 animate-pulse cursor-not-allowed'
                    : chartMode === stat.mode
                      ? 'bg-primary/10 border-primary shadow-sm scale-[1.02]'
                      : 'bg-muted/30 hover:bg-muted/50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span
                    className={`text-xs font-medium ${chartMode === stat.mode ? 'text-primary' : 'text-foreground/80'}`}
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
                    className={`text-xl font-bold tabular-nums ${chartMode === stat.mode ? 'text-primary' : 'text-foreground'}`}
                  >
                    {loading ? '-' : stat.value}
                  </span>
                  {stat.unit && !loading && (
                    <span className="text-xs font-medium text-foreground/70">{stat.unit}</span>
                  )}
                </div>
                <div className="text-[10px] text-muted-foreground">{stat.subtitle}</div>
              </button>
            ))}
          </div>

          <div className="h-56">
            {chartData.length === 0 ? (
              <div className="flex items-center justify-center h-full text-center text-muted-foreground">
                <p className="text-sm">暫無直播數據</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
                  <defs>
                    <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.5} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0.05} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" opacity={0.5} />
                  <XAxis
                    dataKey="date"
                    tick={(props: CustomTickProps) => <CustomTick {...props} />}
                    tickLine={false}
                    axisLine={{ className: 'stroke-border' }}
                  />
                  <YAxis
                    width={35} // 增加寬度確保顯示 10 以上的數字
                    tick={(props: CustomTickProps) => <CustomYAxisTick {...props} />}
                    tickLine={false}
                    axisLine={{ className: 'stroke-border' }}
                  />
                  <Tooltip
                    content={props => <ChartTooltip {...props} chartConfig={chartConfig} />}
                    cursor={{
                      stroke: 'hsl(var(--primary))',
                      strokeWidth: 1,
                      strokeDasharray: '5 5',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey={chartConfig.dataKey}
                    stroke="hsl(var(--primary))"
                    strokeWidth={2.5}
                    fillOpacity={1}
                    fill="url(#colorValue)"
                    activeDot={{ r: 6, fill: 'hsl(var(--primary))', strokeWidth: 2 }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
