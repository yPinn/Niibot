import { Fragment } from 'react'

import type { CloudflareUsage, RateLimitSnapshot } from '@/api/admin'
import { Icon } from '@/components/primitives'
import { Badge, Progress, Skeleton } from '@/components/ui'

import {
  cloudflareRatio,
  cloudflareSeverity,
  formatWindow,
  rankByPressure,
  type Severity,
  severity,
  SEVERITY_BAR,
  SEVERITY_TEXT,
  usageRatio,
  worstSeverity,
} from './rateLimits'
import { CardLinkButton, FieldRow, MonitorCard, Separator } from './StatusCards'

const SEVERITY_BADGE: Record<
  Severity,
  { label: string; icon: string; variant: 'muted' | 'online' | 'warning' | 'offline' }
> = {
  idle: { label: 'idle', icon: 'fa-solid fa-moon', variant: 'muted' },
  ok: { label: 'ok', icon: 'fa-solid fa-circle-check', variant: 'online' },
  warn: { label: 'busy', icon: 'fa-solid fa-triangle-exclamation', variant: 'warning' },
  hot: { label: 'limited', icon: 'fa-solid fa-gauge-high', variant: 'offline' },
}

export function SeverityBadge({ level }: { level: Severity }) {
  const { label, icon, variant } = SEVERITY_BADGE[level]
  return (
    <Badge variant={variant} className="gap-1.5">
      <Icon icon={icon} size="xs" />
      {label}
    </Badge>
  )
}

function usageText(s: RateLimitSnapshot): string {
  if (s.limited) return 'throttled'
  const p = s.provider
  if (p?.limit && p.remaining !== null) return `剩 ${p.remaining}/${p.limit}`
  if (s.limit) {
    const win = formatWindow(s.window_seconds)
    return `${s.used}/${s.limit}${win ? ` · ${win}` : ''}`
  }
  return '—'
}

/** One throttle: name, usage, a severity-coloured meter, and trouble counters. */
export function RateLimitRow({
  snap,
  compact = false,
}: {
  snap: RateLimitSnapshot
  compact?: boolean
}) {
  const level = severity(snap)
  const ratio = usageRatio(snap)
  const counters = [
    snap.rejected ? `拒絕 ${snap.rejected}` : null,
    snap.queued ? `排隊 ${snap.queued}` : null,
    snap.blocked_seconds ? `暫停 ${snap.blocked_seconds}s` : null,
    !compact && snap.keys > 1 ? `${snap.keys} keys` : null,
  ].filter(Boolean)
  return (
    <div className="flex flex-col gap-1 py-2" data-testid="rate-limit-row">
      <div className="flex items-baseline justify-between gap-element">
        <span className="min-w-0 truncate font-mono text-sub" title={snap.name}>
          {snap.name}
        </span>
        <span className={`shrink-0 font-mono text-label ${SEVERITY_TEXT[level]}`}>
          {usageText(snap)}
        </span>
      </div>
      {ratio !== null && (
        <Progress
          segments={[{ value: ratio * 100, className: SEVERITY_BAR[level] }]}
          aria-label={`${snap.name} 用量`}
        />
      )}
      {counters.length > 0 && (
        <span className="text-label text-muted-foreground">{counters.join(' · ')}</span>
      )}
    </div>
  )
}

function RateLimitList({ items }: { items: RateLimitSnapshot[] }) {
  return (
    <>
      {items.map((s, i) => (
        <Fragment key={s.name}>
          {i > 0 && <Separator className="opacity-40" />}
          <RateLimitRow snap={s} compact />
        </Fragment>
      ))}
    </>
  )
}

/** A service card's digest: the three most pressing throttles. */
export function RateLimitDigest({
  items,
  offline,
  failed,
  onOpen,
}: {
  /** undefined while loading; null when the service is offline. */
  items: RateLimitSnapshot[] | null | undefined
  offline?: boolean
  /** The rate-limit request itself failed and there is no earlier data. */
  failed?: boolean
  onOpen: () => void
}) {
  const active = items ? rankByPressure(items).filter(s => severity(s) !== 'idle') : []
  return (
    <>
      <Separator className="opacity-40" />
      <FieldRow
        label="rate limits"
        loading={items === undefined && !failed}
        value={
          failed && !items ? (
            <span className="text-muted-foreground">無法載入</span>
          ) : offline || !items ? (
            <span className="text-muted-foreground">服務離線</span>
          ) : active.length === 0 ? (
            <span className="text-muted-foreground">{items.length} 項皆閒置</span>
          ) : (
            <SeverityBadge level={worstSeverity(items)} />
          )
        }
      />
      {!offline && active.length > 0 && <RateLimitList items={active.slice(0, 3)} />}
      <CardLinkButton onClick={onOpen}>查看限流</CardLinkButton>
    </>
  )
}

/** A titled group of throttles (限流 tab). */
export function RateLimitSection({
  title,
  icon,
  items,
  failed,
}: {
  title: string
  icon: string
  /** null: the service is offline; undefined: still loading. */
  items: RateLimitSnapshot[] | null | undefined
  /** The rate-limit request itself failed and there is no earlier data. Not
   *  the same as the service being offline — never render it as offline. */
  failed?: boolean
}) {
  const loadFailed = failed && items === undefined
  return (
    <MonitorCard
      icon={icon}
      title={title}
      loading={items === undefined && !failed}
      badge={
        loadFailed ? (
          <Badge variant="muted">error</Badge>
        ) : items === null ? (
          <Badge variant="offline">offline</Badge>
        ) : (
          <SeverityBadge level={worstSeverity(items ?? [])} />
        )
      }
    >
      {loadFailed ? (
        <p className="text-sub text-muted-foreground">無法載入限流狀態</p>
      ) : items === undefined ? (
        <Skeleton className="h-24 w-full" />
      ) : items === null ? (
        <p className="text-sub text-muted-foreground">服務離線，無法取得限流狀態</p>
      ) : items.length === 0 ? (
        <p className="text-sub text-muted-foreground">沒有登記的限流</p>
      ) : (
        <RateLimitList items={rankByPressure(items)} />
      )}
    </MonitorCard>
  )
}

function formatTaipei(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('zh-TW', {
    timeZone: 'Asia/Taipei',
    hour12: false,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Cloudflare Workers + Pages Functions daily quota (Free plan: 100k/day). */
export function CloudflareQuotaCard({
  usage,
  failed,
}: {
  /** undefined while loading. */
  usage: CloudflareUsage | undefined
  failed?: boolean
}) {
  const ratio = usage ? cloudflareRatio(usage) : null
  const level = usage ? cloudflareSeverity(usage) : 'idle'
  const configured = !!usage?.configured
  return (
    <MonitorCard
      icon="fa-brands fa-cloudflare"
      title="Cloudflare"
      loading={usage === undefined && !failed}
      badge={
        failed ? (
          <Badge variant="muted">error</Badge>
        ) : !configured ? (
          <Badge variant="muted">未設定</Badge>
        ) : (
          <SeverityBadge level={level} />
        )
      }
    >
      {failed ? (
        <p className="text-sub text-muted-foreground">無法載入用量</p>
      ) : usage === undefined ? (
        <Skeleton className="h-16 w-full" />
      ) : !configured ? (
        <p className="text-sub text-muted-foreground">
          設定 CLOUDFLARE_ACCOUNT_ID 與 CLOUDFLARE_API_TOKEN 後顯示 Workers／Pages Functions
          今日用量。
        </p>
      ) : (
        <>
          <FieldRow
            label="今日請求"
            value={
              <span className={SEVERITY_TEXT[level]}>
                {usage.total_requests?.toLocaleString() ?? '—'} / {usage.limit.toLocaleString()}
              </span>
            }
          />
          {ratio !== null && (
            <Progress
              segments={[{ value: ratio * 100, className: SEVERITY_BAR[level] }]}
              aria-label="Cloudflare 今日用量"
            />
          )}
          <Separator className="mt-element opacity-40" />
          <FieldRow
            label="workers · pages"
            value={`${usage.workers_requests?.toLocaleString() ?? '—'} · ${usage.pages_requests?.toLocaleString() ?? '—'}`}
          />
          <Separator className="opacity-40" />
          <FieldRow label="重置" value={formatTaipei(usage.reset_at)} />
          {usage.errors.map(e => (
            <p key={e} className="font-mono text-label text-status-warning">
              {e}
            </p>
          ))}
        </>
      )}
    </MonitorCard>
  )
}
