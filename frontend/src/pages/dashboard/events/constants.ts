/**
 * Event display metadata is served by `GET /api/events/catalog` — see
 * `EventDefinition` in `@/api/events`. The only things kept here are the
 * accent-token → Tailwind class map (Tailwind v4 can't emit dynamically
 * composed class names, so these must be literal strings) and the redemption
 * action labels, which are not catalog-driven.
 */

export const ACCENT_CLASSES: Record<string, string> = {
  info: 'bg-status-info/10 text-status-info',
  special: 'bg-status-special/10 text-status-special',
  offline: 'bg-status-offline/10 text-status-offline',
  loading: 'bg-status-loading/10 text-status-loading',
  follow: 'bg-status-follow/10 text-status-follow',
  success: 'bg-status-success/10 text-status-success',
  warning: 'bg-status-warning/10 text-status-warning',
  online: 'bg-status-online/10 text-status-online',
}

export function accentClass(accent: string): string {
  return ACCENT_CLASSES[accent] ?? 'bg-muted text-muted-foreground'
}
