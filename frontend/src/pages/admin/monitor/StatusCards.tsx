import { useState } from 'react'

import type { CacheGauge, DbPoolGauge } from '@/api/bots'
import { Icon } from '@/components/primitives'
import {
  Badge,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Separator,
  Skeleton,
} from '@/components/ui'

import { type Severity, SEVERITY_BAR } from './rateLimits'

const DASH = <span className="text-muted-foreground/40">—</span>

export function StatusBadge({ online, ready }: { online: boolean; ready?: boolean }) {
  if (!online)
    return (
      <Badge variant="offline" className="gap-1.5">
        <Icon icon="fa-solid fa-circle-xmark" size="xs" />
        offline
      </Badge>
    )
  if (ready === false)
    return (
      <Badge variant="loading" className="gap-1.5">
        <Icon icon="fa-solid fa-circle-half-stroke" size="xs" />
        starting
      </Badge>
    )
  return (
    <Badge variant="online" className="gap-1.5">
      <Icon icon="fa-solid fa-circle-check" size="xs" />
      online
    </Badge>
  )
}

export function EnvBadge({ env }: { env?: string }) {
  if (!env) return <span className="text-muted-foreground/40">—</span>
  const variant = env === 'production' ? 'live' : env === 'staging' ? 'loading' : 'info'
  return (
    <Badge variant={variant} className="font-mono">
      {env}
    </Badge>
  )
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
      <div className="text-sub font-mono flex min-w-0 items-center break-all">
        {loading ? <Skeleton className="h-4 w-20" /> : offline ? DASH : value}
      </div>
    </div>
  )
}

/** DB pool + cache occupancy for one service — the full breakdown (25+
 * caches, twitch's per-channel memory dict) is too much for a compact
 * FieldRow, so it's collapsed behind an expand toggle. The same JSON
 * pretty-print is what `RUNTIME.GAUGES` log lines show, so the two stay
 * cross-referenceable. */
export function GaugeDetails({
  dbPool,
  caches,
  memory,
}: {
  dbPool?: DbPoolGauge
  caches?: Record<string, CacheGauge>
  memory?: Record<string, number>
}) {
  const [open, setOpen] = useState(false)
  if (!dbPool && !caches && !memory) return null

  const warmCaches = caches ? Object.values(caches).filter(c => c.size > 0).length : 0
  const totalCaches = caches ? Object.keys(caches).length : 0

  return (
    <>
      {dbPool && (
        <>
          <Separator className="opacity-40" />
          <FieldRow
            label="db pool"
            value={`${dbPool.size}/${dbPool.max_size}（閒置 ${dbPool.idle}）`}
          />
        </>
      )}
      {caches && (
        <>
          <Separator className="opacity-40" />
          <FieldRow
            label="caches"
            value={
              <button
                onClick={() => setOpen(o => !o)}
                className="text-muted-foreground hover:text-foreground"
              >
                {warmCaches}/{totalCaches} 有資料 {open ? '收起' : '展開'}
              </button>
            }
          />
        </>
      )}
      {open && (
        <pre className="mt-1 max-h-64 overflow-auto rounded bg-black/30 p-2 text-sub text-muted-foreground/80">
          {JSON.stringify({ ...(caches && { caches }), ...(memory && { memory }) }, null, 2)}
        </pre>
      )}
    </>
  )
}

/** The Monitor's card frame: icon + title, a status badge (skeleton while
 *  loading) in the header action slot, then the body. */
export function MonitorCard({
  icon,
  title,
  badge,
  loading,
  children,
}: {
  icon: string
  title: string
  badge: React.ReactNode
  loading?: boolean
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon={icon} size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">{title}</CardTitle>
        </div>
        <CardAction>{loading ? <Skeleton className="h-5 w-16 rounded-full" /> : badge}</CardAction>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  )
}

/** The quiet "→" link at the foot of a Monitor card that jumps to a tab. */
export function CardLinkButton({
  onClick,
  children,
}: {
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <div className="flex justify-end pt-element">
      <button onClick={onClick} className="text-label text-muted-foreground hover:text-foreground">
        {children} →
      </button>
    </div>
  )
}

/** One at-a-glance fact in the 總覽 summary strip; clickable when it has a tab. */
export function SummaryPill({
  label,
  value,
  level,
  loading,
  onClick,
}: {
  label: string
  value: React.ReactNode
  level: Severity
  loading?: boolean
  onClick?: () => void
}) {
  const body = (
    <>
      <span className={`size-1.5 shrink-0 rounded-full ${SEVERITY_BAR[level]}`} aria-hidden />
      <span className="text-label text-muted-foreground">{label}</span>
      {loading ? (
        <Skeleton className="h-4 w-10" />
      ) : (
        <span className="font-mono text-sub">{value}</span>
      )}
    </>
  )
  const cls = 'flex items-center gap-element rounded-full border border-border/50 px-3 py-1'
  return onClick ? (
    <button onClick={onClick} className={`${cls} transition-colors hover:bg-accent/50`}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  )
}

export { Separator }
