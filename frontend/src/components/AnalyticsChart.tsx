import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { Card, CardContent } from '@/components/ui/card'
import { Icon } from '@/components/ui/icon'

interface AnalyticsData {
  totalStreamHours: number
  totalSessions: number
  totalCommands: number
  totalFollows: number
  totalSubs: number
  avgSessionDuration: number
}

interface AnalyticsChartProps {
  data?: AnalyticsData | null
  loading?: boolean
  className?: string
}

interface TickProps {
  x: number
  y: number
  payload: { value: string }
}

const CustomTick = ({ x, y, payload }: TickProps) => {
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dy={16}
        textAnchor="middle"
        className="text-xs fill-foreground"
        opacity={0.7}
      >
        {payload.value}
      </text>
    </g>
  )
}

const CustomYAxisTick = ({ x, y, payload }: TickProps) => {
  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        dx={-10}
        dy={4}
        textAnchor="end"
        className="text-xs fill-foreground"
        opacity={0.7}
      >
        {payload.value}
      </text>
    </g>
  )
}

export default function AnalyticsChart({
  data,
  loading = false,
  className = '',
}: AnalyticsChartProps) {
  const defaultData: AnalyticsData = {
    totalStreamHours: 0,
    totalSessions: 0,
    totalCommands: 0,
    totalFollows: 0,
    totalSubs: 0,
    avgSessionDuration: 0,
  }

  const analyticsData = data || defaultData

  const stats = [
    {
      label: '總直播時數',
      value: analyticsData.totalStreamHours.toFixed(1),
      unit: 'h',
      subtitle: `${analyticsData.totalSessions} 場直播`,
      icon: 'fa-solid fa-clock',
    },
    {
      label: '總指令使用',
      value: analyticsData.totalCommands,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-terminal',
    },
    {
      label: '新追隨者',
      value: analyticsData.totalFollows,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-user-plus',
    },
    {
      label: '新訂閱者',
      value: analyticsData.totalSubs,
      unit: '',
      subtitle: '過去 30 天',
      icon: 'fa-solid fa-star',
    },
  ]

  const chartData = [
    { date: '12-01', value: 2.5 },
    { date: '12-05', value: 3.2 },
    { date: '12-10', value: 2.8 },
    { date: '12-15', value: 4.1 },
    { date: '12-20', value: 3.5 },
    { date: '12-25', value: 2.9 },
    { date: '12-30', value: 3.8 },
  ]

  return (
    <Card className={className}>
      <CardContent className="p-5">
        <div className="space-y-5">
          <div className="grid grid-cols-4 gap-4">
            {stats.map((stat, index) => (
              <div
                key={index}
                className={`rounded-lg border bg-muted/30 p-4 space-y-2 transition-all duration-300 ${
                  loading ? 'opacity-60 animate-pulse' : 'opacity-100'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-foreground/80">{stat.label}</span>
                  {stat.icon && (
                    <Icon icon={stat.icon} wrapperClassName="size-4 text-muted-foreground" />
                  )}
                </div>

                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-bold tabular-nums text-foreground">
                    {loading ? '-' : stat.value}
                  </span>
                  {stat.unit && !loading && (
                    <span className="text-sm font-medium text-foreground/70">{stat.unit}</span>
                  )}
                </div>

                <div className="text-xs text-muted-foreground">{stat.subtitle}</div>
              </div>
            ))}
          </div>

          <div className="h-56">
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
                  tick={CustomTick as never}
                  tickLine={{ className: 'stroke-border' }}
                  axisLine={{ className: 'stroke-border' }}
                />
                <YAxis
                  tick={CustomYAxisTick as never}
                  tickLine={{ className: 'stroke-border' }}
                  axisLine={{ className: 'stroke-border' }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    boxShadow: '0 4px 12px rgba(0, 0, 0, 0.5)',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                  labelStyle={{ color: 'hsl(var(--popover-foreground))', fontWeight: 600 }}
                  itemStyle={{ color: 'hsl(var(--primary))', fontWeight: 500 }}
                />
                <Area
                  type="monotone"
                  dataKey="value"
                  stroke="hsl(var(--primary))"
                  strokeWidth={2.5}
                  fillOpacity={1}
                  fill="url(#colorValue)"
                  activeDot={{ r: 6, fill: 'hsl(var(--primary))', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
