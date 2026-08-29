import { cn } from '@/lib/utils'

interface ProgressSegment {
  value: number
  className?: string
}

interface ProgressProps {
  /** One or more stacked fill segments, each `value` on the 0..max scale. */
  segments: ProgressSegment[]
  max?: number
  /** Reported as aria-valuenow — defaults to the first segment's value. */
  value?: number
  className?: string
  'aria-label'?: string
}

/**
 * A slim horizontal meter. `segments` stack left-to-right in one track (e.g. a
 * confirmed fill plus a lighter "pending" extension); each is clamped so the
 * running total never exceeds `max`. No Radix — a plain flex track.
 */
function Progress({ segments, max = 100, value, className, ...props }: ProgressProps) {
  const now = value ?? segments[0]?.value ?? 0
  const widths = segments.reduce<number[]>((acc, seg) => {
    const used = acc.reduce((a, b) => a + b, 0)
    acc.push(Math.max(0, Math.min((seg.value / max) * 100, 100 - used)))
    return acc
  }, [])
  return (
    <div
      data-slot="progress"
      role="progressbar"
      aria-valuenow={now}
      aria-valuemin={0}
      aria-valuemax={max}
      className={cn('flex h-1.5 w-full overflow-hidden rounded-full bg-muted', className)}
      {...props}
    >
      {segments.map((seg, i) => (
        <div
          key={i}
          className={cn('bg-primary', seg.className)}
          style={{ width: `${widths[i]}%` }}
        />
      ))}
    </div>
  )
}

export { Progress }
