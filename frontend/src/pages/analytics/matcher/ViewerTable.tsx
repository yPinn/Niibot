import {
  Badge,
  EmptyState,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { formatRelativeDays, formatWatchHours } from '@/lib/format'
import { cn } from '@/lib/utils'

import type { MatcherViewersResponse } from './types'

interface ViewerTableProps {
  data: MatcherViewersResponse | null
  isLoading: boolean
}

function HomeStatus({ sessions }: { sessions: number }) {
  if (sessions === 0) return <span className="text-label text-muted-foreground">從未</span>
  if (sessions <= 2) return <span className="text-label text-status-info">偶爾</span>
  return <span className="text-label text-status-online">熟客</span>
}

function TierBadge({ score }: { score: number }) {
  const [tier, className] =
    score >= 80
      ? (['S', 'text-status-loading border-status-loading/40'] as const)
      : score >= 60
        ? (['A', 'text-status-online border-status-online/40'] as const)
        : score >= 40
          ? (['B', 'text-status-info border-status-info/40'] as const)
          : (['C', 'text-muted-foreground'] as const)
  return (
    <Badge variant="outline" className={cn('font-mono font-bold text-label', className)}>
      {tier}
    </Badge>
  )
}

export function ViewerTable({ data, isLoading }: ViewerTableProps) {
  if (isLoading) {
    return (
      <div className="flex flex-col">
        <div className="flex items-center gap-4 h-10 px-4 border-b">
          <Skeleton className="h-3.5 w-20 rounded" />
          <Skeleton className="h-3.5 w-14 rounded ml-auto" />
          <Skeleton className="h-3.5 w-16 rounded" />
          <Skeleton className="h-3.5 w-12 rounded" />
        </div>
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 h-10 px-4 border-b border-border/40">
            <div className="flex flex-col gap-1 flex-1 max-w-[140px]">
              <Skeleton className="h-3.5 w-full rounded" />
              <Skeleton className="h-2.5 w-16 rounded" />
            </div>
            <div className="ml-auto flex flex-col items-end gap-1">
              <Skeleton className="h-3.5 w-10 rounded" />
              <Skeleton className="h-2.5 w-8 rounded" />
            </div>
            <Skeleton className="h-3.5 w-8 rounded" />
            <Skeleton className="h-5 w-8 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (!data || data.total === 0) {
    return (
      <EmptyState
        className="py-empty"
        icon="fa-solid fa-users"
        title="尚無潛在觀眾資料"
        description="目前找不到與此頻道重疊的觀眾"
      />
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>顯示名稱</TableHead>
          <TableHead className="text-right">在對方頻道</TableHead>
          <TableHead className="text-right">在你的頻道</TableHead>
          <TableHead className="text-right">潛在等級</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.viewers.map(viewer => (
          <TableRow key={viewer.user_id}>
            <TableCell className="font-medium">
              <div className="flex flex-col gap-0.5">
                <span>{viewer.display_name ?? viewer.username}</span>
                {viewer.partner_last_seen && (
                  <span className="text-label text-muted-foreground">
                    {formatRelativeDays(viewer.partner_last_seen)}
                  </span>
                )}
              </div>
            </TableCell>
            <TableCell className="text-right">
              <div className="flex flex-col items-end gap-0.5">
                <span className="text-label font-medium tabular-nums">
                  {formatWatchHours(viewer.partner_watch_sec)}
                </span>
                <span className="text-label text-muted-foreground tabular-nums">
                  {viewer.partner_messages.toLocaleString()} 則
                </span>
              </div>
            </TableCell>
            <TableCell className="text-right">
              <HomeStatus sessions={viewer.home_sessions} />
            </TableCell>
            <TableCell className="text-right">
              <TierBadge score={viewer.potential_score} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
