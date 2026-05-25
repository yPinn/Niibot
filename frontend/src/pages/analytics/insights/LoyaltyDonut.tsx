import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
} from 'recharts'

import type { LoyaltyTiers } from '@/api/analytics'

interface Props {
  tiers: LoyaltyTiers
}

const TIERS = [
  { key: 'core', label: '核心觀眾', desc: '連續 5+ 場', color: 'var(--primary)' },
  { key: 'regular', label: '常客', desc: '連續 2–4 場', color: 'var(--status-info)' },
  { key: 'newcomer', label: '新觀眾', desc: '首次出現', color: 'var(--status-online)' },
] as const

const EMPTY_SLICE = [{ label: '', desc: '', color: 'var(--muted)', value: 1 }]

function ChartTooltip({
  active,
  payload,
}: Pick<TooltipContentProps<number, string>, 'active' | 'payload'>) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as { label: string; desc: string; value: number }
  return (
    <div className="bg-popover border border-border rounded-lg shadow-xl px-3 py-2 text-label">
      <p className="text-foreground font-medium">{d.label}</p>
      <p className="text-muted-foreground">{d.desc}</p>
      <p className="text-primary font-semibold tabular-nums mt-0.5">{d.value} 人</p>
    </div>
  )
}

export function LoyaltyDonut({ tiers }: Props) {
  const data = TIERS.map(t => ({
    label: t.label,
    desc: t.desc,
    color: t.color,
    value: tiers[t.key],
  }))
  const total = data.reduce((s, d) => s + d.value, 0)

  return (
    <div className="flex flex-col gap-3 h-full">
      <div className="relative flex-1 min-h-0" style={{ minHeight: 120 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={total > 0 ? data : EMPTY_SLICE}
              cx="50%"
              cy="50%"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={total > 0 ? 3 : 0}
              dataKey="value"
              strokeWidth={0}
              isAnimationActive={false}
              activeShape={undefined}
            >
              {(total > 0 ? data : EMPTY_SLICE).map(d => (
                <Cell key={d.color} fill={d.color} />
              ))}
            </Pie>
            {total > 0 && (
              <Tooltip
                content={({ active, payload }) => (
                  <ChartTooltip
                    active={active}
                    payload={payload as TooltipContentProps<number, string>['payload']}
                  />
                )}
              />
            )}
          </PieChart>
        </ResponsiveContainer>

        {/* Centre label */}
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-card-title font-bold tabular-nums">{total}</span>
          <span className="text-label text-muted-foreground">觀眾</span>
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-col gap-1.5 shrink-0">
        {data.map(d => (
          <div key={d.label} className="flex items-center justify-between text-label">
            <div className="flex items-center gap-1.5">
              <span className="size-2 rounded-full shrink-0" style={{ background: d.color }} />
              <span className="text-foreground">{d.label}</span>
              <span className="text-muted-foreground">{d.desc}</span>
            </div>
            <span className="font-semibold tabular-nums text-foreground">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
