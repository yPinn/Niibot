import { useState } from 'react'

import type { CacheGauge, DbPoolGauge } from '@/api/bots'
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

export { Separator }
