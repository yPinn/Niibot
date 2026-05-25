import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
  XAxis,
  YAxis,
} from 'recharts'

import type { InsightsGameStat } from '@/api/analytics'

interface Props {
  data: InsightsGameStat[]
}

function ChartTooltip({
  active,
  payload,
}: Pick<TooltipContentProps<number, string>, 'active' | 'payload'>) {
  if (!active || !payload?.length) return null
  const stat = payload[0].payload as InsightsGameStat
  return (
    <div className="bg-popover border border-border rounded-lg shadow-xl px-3 py-2 text-label">
      <p className="text-foreground font-medium mb-1 max-w-48 truncate">{stat.game_name}</p>
      <p className="text-muted-foreground">
        {stat.session_count} 場 · {stat.total_hours.toFixed(1)}h
      </p>
    </div>
  )
}

function truncateGameName(name: string, maxLen = 14): string {
  return name.length > maxLen ? name.slice(0, maxLen - 1) + '…' : name
}

export function TopGamesChart({ data }: Props) {
  const chartData = data.map(d => ({ ...d, shortName: truncateGameName(d.game_name) }))
  const max = Math.max(...chartData.map(d => d.session_count), 1)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 8, left: 4, bottom: 0 }}
      >
        <XAxis
          type="number"
          domain={[0, max + 1]}
          tick={{ fontSize: 'var(--text-label)', fill: 'var(--muted-foreground)' }}
          tickLine={false}
          axisLine={false}
          tickCount={max + 2}
          allowDecimals={false}
        />
        <YAxis
          type="category"
          dataKey="shortName"
          tick={{ fontSize: 'var(--text-label)', fill: 'var(--muted-foreground)' }}
          tickLine={false}
          axisLine={false}
          width={90}
        />
        <Tooltip
          content={({ active, payload }) => (
            <ChartTooltip
              active={active}
              payload={payload as TooltipContentProps<number, string>['payload']}
            />
          )}
          cursor={{ fill: 'color-mix(in oklch, var(--muted) 40%, transparent)' }}
        />
        <Bar dataKey="session_count" radius={[0, 3, 3, 0]} maxBarSize={20}>
          {chartData.map((d, i) => (
            <Cell key={d.game_name} fill="var(--primary)" fillOpacity={1 - i * 0.12} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
