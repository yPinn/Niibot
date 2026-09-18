import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'

const HOURS = Array.from({ length: 24 }, (_, i) => i)

function cellOpacity(value: number, max: number): number {
  if (value <= 0) return 0.12
  if (max <= 0) return 0.12
  return 0.3 + 0.7 * (value / max)
}

interface HourRowProps {
  label: string
  histogram: number[]
  color: string
}

function HourRow({ label, histogram, color }: HourRowProps) {
  const max = Math.max(...histogram, 0)
  return (
    <div className="flex items-center gap-2">
      <span className="text-label text-muted-foreground w-10 shrink-0">{label}</span>
      <div
        className="flex-1"
        style={{ display: 'grid', gridTemplateColumns: 'repeat(24, 1fr)', gap: 2 }}
      >
        {HOURS.map(hour => {
          const value = histogram[hour] ?? 0
          return (
            <Tooltip key={hour}>
              <TooltipTrigger asChild>
                <div
                  role="img"
                  aria-label={`${hour}:00 — ${value} 場`}
                  className="aspect-square rounded-sm cursor-default"
                  style={{ background: color, opacity: cellOpacity(value, max) }}
                />
              </TooltipTrigger>
              <TooltipContent side="top">
                <p className="text-label">
                  {hour}:00 · {value} 場
                </p>
              </TooltipContent>
            </Tooltip>
          )
        })}
      </div>
    </div>
  )
}

interface HourHeatStripProps {
  homeHistogram: number[]
  partnerHistogram: number[]
  partnerLabel: string
}

export function HourHeatStrip({
  homeHistogram,
  partnerHistogram,
  partnerLabel,
}: HourHeatStripProps) {
  const hasData = homeHistogram.some(v => v > 0) || partnerHistogram.some(v => v > 0)
  if (!hasData) return null

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex flex-col gap-1.5">
        <HourRow label="你" histogram={homeHistogram} color="var(--primary)" />
        <HourRow label={partnerLabel} histogram={partnerHistogram} color="var(--status-info)" />
        <div className="flex justify-between pl-12 text-label text-muted-foreground/50">
          <span>0:00</span>
          <span>12:00</span>
          <span>23:00</span>
        </div>
      </div>
    </TooltipProvider>
  )
}
