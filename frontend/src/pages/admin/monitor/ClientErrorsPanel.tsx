import { useCallback, useEffect, useState } from 'react'

import {
  type ClientErrorEvent,
  type ClientErrorGroup,
  type ClientErrorKind,
  getClientErrorEvents,
  getClientErrorGroups,
} from '@/api/admin'
import { Icon, Spinner } from '@/components/primitives'
import { formatRelativeTime } from '@/lib/format'

const KIND_OPTS: { value: ClientErrorKind | 'all'; label: string }[] = [
  { value: 'all', label: '全部' },
  { value: 'react', label: 'React' },
  { value: 'error', label: 'JS' },
  { value: 'unhandledrejection', label: 'Promise' },
  { value: 'api', label: 'API' },
]

const SINCE_OPTS: { value: number; label: string }[] = [
  { value: 24, label: '24 小時' },
  { value: 168, label: '7 天' },
  { value: 336, label: '14 天' },
]

function kindBadgeClass(kind: ClientErrorKind): string {
  switch (kind) {
    case 'react':
      return 'bg-status-info/15 text-status-info'
    case 'api':
      return 'bg-status-warning/15 text-status-warning'
    default:
      return 'bg-status-offline/15 text-status-offline'
  }
}

function EventDetail({
  event,
  onTraceRequestId,
}: {
  event: ClientErrorEvent
  onTraceRequestId: (requestId: string) => void
}) {
  return (
    <div className="flex flex-col gap-1.5 border-t border-border/30 px-3 py-2 font-mono text-label">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground/70">
        <span>{new Date(event.occurred_at).toLocaleString('zh-TW', { hour12: false })}</span>
        {event.http_status && <span>HTTP {event.http_status}</span>}
        {event.error_code && <span>{event.error_code}</span>}
        {event.app_version && <span>v{event.app_version}</span>}
        {event.request_id && (
          <button
            onClick={() => onTraceRequestId(event.request_id!)}
            title="在 API log 中追蹤此請求"
            className="flex items-center gap-1 rounded bg-muted-foreground/10 px-1.5 text-status-info hover:bg-muted-foreground/20"
          >
            <Icon icon="fa-solid fa-arrow-right-to-bracket" size="xs" />
            {event.request_id.slice(0, 8)}
          </button>
        )}
      </div>
      <div className="break-all text-muted-foreground/60">{event.url}</div>
      {event.stack && (
        <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-muted-foreground/80">
          {event.stack}
        </pre>
      )}
      {event.component_stack && (
        <pre className="overflow-x-auto rounded bg-muted/50 p-2 text-muted-foreground/60">
          {event.component_stack}
        </pre>
      )}
    </div>
  )
}

function GroupRow({
  group,
  onTraceRequestId,
}: {
  group: ClientErrorGroup
  onTraceRequestId: (requestId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [events, setEvents] = useState<ClientErrorEvent[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const toggle = () => {
    const next = !open
    setOpen(next)
    if (next && events === null && !loading) {
      setLoading(true)
      setError(null)
      getClientErrorEvents(group.fingerprint)
        .then(setEvents)
        .catch(e => setError(e instanceof Error ? e.message : String(e)))
        .finally(() => setLoading(false))
    }
  }

  return (
    <div className="border-b border-border/40">
      <button
        onClick={toggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-accent/50"
      >
        <Icon
          icon={`fa-solid fa-chevron-${open ? 'down' : 'right'}`}
          size="xs"
          wrapperClassName="text-muted-foreground/50 shrink-0"
        />
        <span
          className={`shrink-0 rounded px-1.5 text-label font-mono ${kindBadgeClass(group.kind)}`}
        >
          {group.kind}
        </span>
        <span className="shrink-0 rounded bg-muted-foreground/15 px-1.5 text-label font-mono tabular-nums text-muted-foreground">
          ×{group.count}
        </span>
        <span className="min-w-0 flex-1 truncate text-sub">{group.message}</span>
        {group.route && (
          <span className="hidden shrink-0 font-mono text-label text-muted-foreground/50 sm:inline">
            {group.route}
          </span>
        )}
        <span className="shrink-0 font-mono text-label text-muted-foreground/50">
          {formatRelativeTime(group.last_seen)}
        </span>
      </button>

      {open && (
        <div className="bg-muted/20">
          {loading && (
            <div className="flex items-center gap-2 px-3 py-2 text-label text-muted-foreground">
              <Spinner className="size-3" />
              載入明細中…
            </div>
          )}
          {error && <div className="px-3 py-2 text-label text-destructive">{error}</div>}
          {events?.length === 0 && (
            <div className="px-3 py-2 text-label text-muted-foreground">沒有明細</div>
          )}
          {events?.map((ev, i) => (
            <EventDetail key={i} event={ev} onTraceRequestId={onTraceRequestId} />
          ))}
        </div>
      )}
    </div>
  )
}

export function ClientErrorsPanel({
  onTraceRequestId,
  reloadNonce,
  onLoadingChange,
}: {
  onTraceRequestId: (requestId: string) => void
  /** Bump to force a reload from the parent's shared refresh button. */
  reloadNonce?: number
  onLoadingChange?: (loading: boolean) => void
}) {
  const [kind, setKind] = useState<ClientErrorKind | 'all'>('all')
  const [sinceHours, setSinceHours] = useState(168)
  const [groups, setGroups] = useState<ClientErrorGroup[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    setLoading(true)
    setError(null)
    getClientErrorGroups({ sinceHours, kind: kind === 'all' ? undefined : kind })
      .then(setGroups)
      .catch(e => setError(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false))
  }, [kind, sinceHours])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load()
  }, [load, reloadNonce])

  useEffect(() => {
    onLoadingChange?.(loading)
    return () => onLoadingChange?.(false)
  }, [loading, onLoadingChange])

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden bg-background">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 border-b border-border/30 px-page py-1.5 shrink-0">
        <div className="flex items-center gap-0.5">
          {KIND_OPTS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setKind(opt.value)}
              className={`rounded px-2 py-0.5 text-label font-mono transition-colors select-none ${
                kind === opt.value
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground/50 hover:text-muted-foreground hover:bg-accent/50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <div className="mx-1 h-4 w-px bg-border/50" />
        <div className="flex items-center gap-0.5">
          {SINCE_OPTS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setSinceHours(opt.value)}
              className={`rounded px-2 py-0.5 text-label font-mono transition-colors select-none ${
                sinceHours === opt.value
                  ? 'bg-accent text-accent-foreground'
                  : 'text-muted-foreground/50 hover:text-muted-foreground hover:bg-accent/50'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading && groups.length === 0 ? (
          <div className="flex items-center gap-2 px-page py-3 text-muted-foreground">
            <Spinner className="size-3" />
            <span>載入前端錯誤中…</span>
          </div>
        ) : error ? (
          <div className="px-page py-3 text-destructive">{error}</div>
        ) : groups.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 py-16 text-muted-foreground/60">
            <Icon icon="fa-solid fa-shield-check" size="lg" />
            <span className="text-sub">這段期間沒有前端錯誤</span>
          </div>
        ) : (
          groups.map(g => (
            <GroupRow key={g.fingerprint} group={g} onTraceRequestId={onTraceRequestId} />
          ))
        )}
      </div>
    </div>
  )
}
