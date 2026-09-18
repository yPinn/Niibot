import { Badge } from '@/components/ui'

export function broadcasterBadge(type: string | null) {
  if (type === 'partner')
    return (
      <Badge
        variant="outline"
        className="text-status-loading border-status-loading/40 text-label py-0 shrink-0"
      >
        Partner
      </Badge>
    )
  if (type === 'affiliate')
    return (
      <Badge variant="outline" className="text-primary border-primary/40 text-label py-0 shrink-0">
        Affiliate
      </Badge>
    )
  return null
}

export function overlapColor(pct: number): string {
  if (pct >= 30) return 'text-status-online'
  if (pct >= 10) return 'text-status-info'
  return 'text-muted-foreground'
}
