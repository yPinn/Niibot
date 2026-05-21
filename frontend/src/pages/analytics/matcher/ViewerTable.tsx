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

import type { MatcherViewersResponse } from './types'

interface ViewerTableProps {
  data: MatcherViewersResponse | null
  isLoading: boolean
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
          <TableHead className="text-right">對方場次</TableHead>
          <TableHead className="text-right">對方訊息</TableHead>
          <TableHead className="text-right">你的頻道場次</TableHead>
          <TableHead className="text-right">潛在分數</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {data.viewers.map(viewer => (
          <TableRow key={viewer.user_id}>
            <TableCell className="font-medium">{viewer.display_name ?? viewer.username}</TableCell>
            <TableCell className="text-right tabular-nums">
              {viewer.partner_sessions.toLocaleString()}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {viewer.partner_messages.toLocaleString()}
            </TableCell>
            <TableCell className="text-right tabular-nums">
              {viewer.home_sessions === 0 ? (
                <span className="text-muted-foreground">從未</span>
              ) : (
                viewer.home_sessions.toLocaleString()
              )}
            </TableCell>
            <TableCell className="text-right">
              <Badge variant="secondary" className="tabular-nums font-mono">
                {viewer.potential_score.toFixed(1)}
              </Badge>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
