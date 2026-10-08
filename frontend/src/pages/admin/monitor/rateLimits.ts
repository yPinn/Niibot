import type { CloudflareUsage, RateLimitGroup, RateLimitSnapshot } from '@/api/admin'

/** idle: nothing in the window · ok · warn: worth a look · hot: throttling now. */
export type Severity = 'idle' | 'ok' | 'warn' | 'hot'

const SEVERITY_RANK: Record<Severity, number> = { hot: 3, warn: 2, ok: 1, idle: 0 }

/** A rejection this recent still colours the row. */
const RECENT_REJECTION_SECONDS = 15 * 60

export const GROUP_LABEL: Record<RateLimitGroup, string> = {
  inbound: 'API 入站',
  twitch: 'Twitch',
  discord: 'Discord',
  egress: '對外連線',
}

/**
 * 0..1 share of the budget in use, or null when the throttle has no cap to
 * compare against. A provider-reported budget (Twitch `Ratelimit-*`) is the
 * real constraint, so it wins over our own pacing gate.
 */
export function usageRatio(s: RateLimitSnapshot): number | null {
  if (s.limited) return 1
  const p = s.provider
  if (p?.limit && p.remaining !== null) return clamp01((p.limit - p.remaining) / p.limit)
  if (s.limit) return clamp01(s.used / s.limit)
  return null
}

export function severity(s: RateLimitSnapshot, nowSeconds = Date.now() / 1000): Severity {
  const ratio = usageRatio(s)
  if (s.limited || (s.blocked_seconds ?? 0) > 0 || (ratio !== null && ratio >= 0.9)) return 'hot'
  const recentRejection =
    s.last_rejected_at != null && nowSeconds - s.last_rejected_at < RECENT_REJECTION_SECONDS
  if (recentRejection || (s.queued ?? 0) > 0 || (ratio !== null && ratio >= 0.6)) return 'warn'
  if (s.used === 0 && s.keys === 0 && !s.rejected) return 'idle'
  return 'ok'
}

/** Most pressing first: severity, then share used, then name. */
export function rankByPressure(
  list: RateLimitSnapshot[],
  nowSeconds = Date.now() / 1000
): RateLimitSnapshot[] {
  return [...list].sort(
    (a, b) =>
      SEVERITY_RANK[severity(b, nowSeconds)] - SEVERITY_RANK[severity(a, nowSeconds)] ||
      (usageRatio(b) ?? -1) - (usageRatio(a) ?? -1) ||
      a.name.localeCompare(b.name)
  )
}

/** The worst severity in a list — what a service card's badge shows. */
export function worstSeverity(list: RateLimitSnapshot[], nowSeconds = Date.now() / 1000): Severity {
  return list.reduce<Severity>((worst, s) => {
    const sev = severity(s, nowSeconds)
    return SEVERITY_RANK[sev] > SEVERITY_RANK[worst] ? sev : worst
  }, 'idle')
}

export function formatWindow(seconds: number | null): string {
  if (!seconds) return ''
  if (seconds < 60) return `${seconds}s`
  if (seconds % 3600 === 0) return `${seconds / 3600}h`
  if (seconds % 60 === 0) return `${seconds / 60}m`
  return `${Math.round(seconds)}s`
}

export function cloudflareRatio(u: CloudflareUsage): number | null {
  if (!u.configured || u.total_requests === null || !u.limit) return null
  return clamp01(u.total_requests / u.limit)
}

export function cloudflareSeverity(u: CloudflareUsage): Severity {
  const ratio = cloudflareRatio(u)
  if (ratio === null) return 'idle'
  if (ratio >= 0.9) return 'hot'
  if (ratio >= 0.6) return 'warn'
  return 'ok'
}

/** Tailwind classes per severity — status tokens, never raw colours. */
export const SEVERITY_BAR: Record<Severity, string> = {
  idle: 'bg-muted-foreground/30',
  ok: 'bg-status-online',
  warn: 'bg-status-warning',
  hot: 'bg-status-offline',
}

export const SEVERITY_TEXT: Record<Severity, string> = {
  idle: 'text-muted-foreground',
  ok: 'text-status-online',
  warn: 'text-status-warning',
  hot: 'text-status-offline',
}

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n))
}
