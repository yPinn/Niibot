import { Icon } from '@/components/ui'

export function SummaryTile({
  icon,
  value,
  label,
  iconClassName,
}: {
  icon: string
  value: string
  label: string
  iconClassName?: string
}) {
  return (
    <div className="rounded-md border px-2.5 py-2 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <p className="text-label text-muted-foreground">{label}</p>
        <Icon
          icon={icon}
          size="xs"
          wrapperClassName={iconClassName ?? 'text-muted-foreground/60'}
        />
      </div>
      <p className="text-content font-bold tabular-nums">{value}</p>
    </div>
  )
}
