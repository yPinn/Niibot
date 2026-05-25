import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from 'recharts'

import type { SessionChartPoint } from '@/api/analytics'

interface Props {
  data: SessionChartPoint[]
}

const DATE_FMT = new Intl.DateTimeFormat('zh-TW', { month: 'numeric', day: 'numeric' })

function ChartTooltip({
  active,
  payload,
}: Pick<TooltipContentProps<number, string>, 'active' | 'payload'>) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload as SessionChartPoint & { label: string }
  return (
    <div className="bg-popover border border-border rounded-lg shadow-xl px-3 py-2 text-label">
      <p className="text-muted-foreground mb-1">{point.label}</p>
      {point.game_name && <p className="text-foreground truncate max-w-40">{point.game_name}</p>}
      <p className="text-primary font-semibold tabular-nums">
        {(payload[0].value as number).toFixed(1)} 觀看時數
      </p>
    </div>
  )
}

export function SessionWatchChart({ data }: Props) {
  const chartData = data.map(p => ({
    ...p,
    label: DATE_FMT.format(new Date(p.started_at)),
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" className="stroke-border" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 'var(--text-label)', fill: 'var(--muted-foreground)' }}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={{ fontSize: 'var(--text-label)', fill: 'var(--muted-foreground)' }}
          tickLine={false}
          axisLine={false}
          width={36}
        />
        <Tooltip
          content={({ active, payload }) => (
            <ChartTooltip
              active={active}
              payload={payload as TooltipContentProps<number, string>['payload']}
            />
          )}
          cursor={{ fill: 'var(--muted)/0.3' }}
        />
        <Bar
          dataKey="total_watch_hours"
          fill="var(--primary)"
          radius={[3, 3, 0, 0]}
          maxBarSize={32}
        />
      </BarChart>
    </ResponsiveContainer>
  )
}
