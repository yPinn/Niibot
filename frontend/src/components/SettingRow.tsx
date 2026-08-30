import { cn } from '@/lib/utils'

interface SettingRowProps {
  /** Row label. Accepts nodes so a <Badge> can sit inline. */
  title: React.ReactNode
  description?: React.ReactNode
  /** The right-aligned control (usually a <Switch>). */
  children: React.ReactNode
  /** Extra classes for the outer row (e.g. a border for list-item variants). */
  className?: string
}

/**
 * `label + description` on the left, a control on the right — the shape every
 * settings sheet repeats. See EventSheet, CommandSheet, Timers, Modules.
 */
export function SettingRow({ title, description, children, className }: SettingRowProps) {
  return (
    <div className={cn('flex items-center justify-between gap-4', className)}>
      <div className="flex min-w-0 flex-col gap-0.5">
        <span className="flex items-center gap-1.5 text-sub font-medium leading-none">{title}</span>
        {description && <span className="text-label text-muted-foreground">{description}</span>}
      </div>
      {children}
    </div>
  )
}
