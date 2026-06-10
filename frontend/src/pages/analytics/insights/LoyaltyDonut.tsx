import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  type TooltipContentProps,
} from 'recharts'

export interface SessionTiers {
  core: number
  regular: number
  newcomer: number
  silent: number
}

interface Props {
  tiers: SessionTiers
}

const TIER_DEFS = [
  { key: 'core', label: '核心觀眾', desc: '前 25%（前標）', color: 'var(--primary)' },
  { key: 'regular', label: '常駐觀眾', desc: '前 50%（均標）', color: 'var(--status-info)' },
  { key: 'newcomer', label: '新進觀眾', desc: '後 50%（近期追隨）', color: 'var(--status-online)' },
  {
    key: 'silent',
    label: '沉默觀眾',
    desc: '後 50%（早期追隨）',
    color: 'var(--muted-foreground)',
  },
] as const satisfies ReadonlyArray<{
  key: keyof SessionTiers
  label: string
  desc: string
  color: string
}>

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
  const data = TIER_DEFS.map(t => ({
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
              data={data}
              cx="50%"
              cy="50%"
              innerRadius="55%"
              outerRadius="80%"
              paddingAngle={3}
              dataKey="value"
              strokeWidth={0}
              isAnimationActive={false}
              activeShape={undefined}
            >
              {data.map(d => (
                <Cell key={d.color} fill={d.color} />
              ))}
            </Pie>
            <Tooltip
              content={({ active, payload }) => (
                <ChartTooltip
                  active={active}
                  payload={payload as TooltipContentProps<number, string>['payload']}
                />
              )}
            />
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
