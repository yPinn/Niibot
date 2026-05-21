import {
  Badge,
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Icon,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { cn } from '@/lib/utils'

import type { MatcherViewersResponse } from './types'

interface ViewerTableProps {
  data: MatcherViewersResponse | null
  isLoading: boolean
}

function ActivityDots({ value, thresholds }: { value: number; thresholds: [number, number] }) {
  const level = value >= thresholds[1] ? 3 : value >= thresholds[0] ? 2 : value > 0 ? 1 : 0
  return (
    <div className="flex gap-0.5 justify-end">
      {[1, 2, 3].map(i => (
        <span
          key={i}
          className={cn(
            'size-2 rounded-full',
            i <= level ? 'bg-foreground/70' : 'bg-muted-foreground/20'
          )}
        />
      ))}
    </div>
  )
}

function HomeStatus({ sessions }: { sessions: number }) {
  if (sessions === 0) return <span className="text-label text-muted-foreground">從未</span>
  if (sessions <= 2) return <span className="text-label text-blue-500">偶爾</span>
  return <span className="text-label text-green-500">熟客</span>
}

function TierBadge({ score }: { score: number }) {
  const [tier, className] =
    score >= 80
      ? (['S', 'text-yellow-500 border-yellow-500/40'] as const)
      : score >= 60
        ? (['A', 'text-green-500 border-green-500/40'] as const)
        : score >= 40
          ? (['B', 'text-blue-500 border-blue-500/40'] as const)
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
      <div className="space-y-1">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full rounded-md" />
        ))}
      </div>
    )
  }

  if (!data || data.total === 0) {
    return (
      <Empty className="border-none py-empty">
        <EmptyHeader>
          <EmptyMedia>
            <Icon
              icon="fa-solid fa-users"
              wrapperClassName="size-20 opacity-25"
              className="text-[5rem]"
            />
          </EmptyMedia>
          <EmptyTitle>尚無潛在觀眾資料</EmptyTitle>
        </EmptyHeader>
      </Empty>
    )
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>顯示名稱</TableHead>
          <TableHead className="text-right">對方活躍度</TableHead>
          <TableHead className="text-right">在你的頻道</TableHead>
          <TableHead className="text-right">潛在等級</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.viewers.map(viewer => (
          <TableRow key={viewer.user_id}>
            <TableCell className="font-medium">{viewer.display_name ?? viewer.username}</TableCell>
            <TableCell className="text-right">
              {/* partner_sessions: low ≥1, med ≥5, high ≥12 */}
              <ActivityDots value={viewer.partner_sessions} thresholds={[5, 12]} />
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
