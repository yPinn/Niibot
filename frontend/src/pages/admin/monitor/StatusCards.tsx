import { Icon } from '@/components/primitives'
import { Badge, Separator, Skeleton } from '@/components/ui'

const DASH = <span className="text-muted-foreground/40">—</span>

export function StatusBadge({ online, ready }: { online: boolean; ready?: boolean }) {
  if (!online)
    return (
      <Badge className="border-status-offline/20 bg-status-offline/10 text-status-offline gap-1.5">
        <Icon icon="fa-solid fa-circle-xmark" size="xs" />
        offline
      </Badge>
    )
  if (ready === false)
    return (
      <Badge className="border-status-loading/20 bg-status-loading/10 text-status-loading gap-1.5">
        <Icon icon="fa-solid fa-circle-half-stroke" size="xs" />
        starting
      </Badge>
    )
  return (
    <Badge className="border-status-online/20 bg-status-online/10 text-status-online gap-1.5">
      <Icon icon="fa-solid fa-circle-check" size="xs" />
      online
    </Badge>
  )
}

export function EnvBadge({ env }: { env?: string }) {
  if (!env) return <span className="text-muted-foreground/40">—</span>
  const cls =
    env === 'production'
      ? 'border-status-live/20 bg-status-live/10 text-status-live'
      : env === 'staging'
        ? 'border-status-loading/20 bg-status-loading/10 text-status-loading'
        : 'border-status-info/20 bg-status-info/10 text-status-info'
  return <Badge className={`font-mono ${cls}`}>{env}</Badge>
}

export function VersionText({ version, commit }: { version?: string; commit?: string }) {
  const label = version && version !== 'dev' ? version : (version ?? '—')
  const shortSha = commit && commit !== 'unknown' ? commit.slice(0, 7) : null
  return <>{shortSha && !label.includes(shortSha) ? `${label} (${shortSha})` : label}</>
}

export function FieldRow({
  label,
  value,
  loading,
  offline,
}: {
  label: string
  value: React.ReactNode
  loading?: boolean
  offline?: boolean
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <span className="text-label font-medium uppercase tracking-wide text-muted-foreground shrink-0">
        {label}
      </span>
      <div className="text-sub font-mono flex items-center">
        {loading ? <Skeleton className="h-4 w-20" /> : offline ? DASH : value}
      </div>
    </div>
  )
}

export { Separator }
