import type { VideoQueueHistoryEntry } from '@/api/videoQueue'
import { Icon } from '@/components/primitives'
import { TableEmptyRow } from '@/components/TableEmptyRow'
import { TableShell } from '@/components/TableShell'
import {
  Badge,
  Button,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { formatRelativeTime } from '@/lib/format'

import { PlatformBadge, SourceBadge } from './QueueTable'

export function HistoryTable({
  entries,
  onRequeue,
  onBlock,
}: {
  entries: VideoQueueHistoryEntry[]
  onRequeue: (entry: VideoQueueHistoryEntry) => void
  onBlock: (entry: VideoQueueHistoryEntry) => void
}) {
  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead>影片</TableHead>
          <TableHead className="w-20 sm:w-28">點播者</TableHead>
          <TableHead className="hidden sm:table-cell w-16 text-center">來源</TableHead>
          <TableHead className="w-16 text-center">狀態</TableHead>
          <TableHead className="hidden sm:table-cell w-24 text-right tabular-nums">時間</TableHead>
          <TableHead className="w-20" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.length === 0 ? (
          <TableEmptyRow
            colSpan={6}
            icon="fa-solid fa-clock-rotate-left"
            title="尚無播放紀錄"
            description="播放或略過的影片會保留 30 天"
          />
        ) : (
          entries.map(entry => (
            <TableRow key={entry.id}>
              <TableCell>
                <div className="flex items-center gap-1.5 min-w-0">
                  <PlatformBadge videoType={entry.video_type} />
                  <span className="truncate" title={entry.title || entry.video_id}>
                    {entry.title || entry.video_id}
                  </span>
                </div>
              </TableCell>
              <TableCell className="text-muted-foreground text-sub">
                <span className="block truncate">{entry.requested_by}</span>
              </TableCell>
              <TableCell className="hidden sm:table-cell text-center">
                <SourceBadge source={entry.source} />
              </TableCell>
              <TableCell className="text-center">
                <Badge
                  variant="outline"
                  className={
                    entry.status === 'done'
                      ? 'text-label border-status-success/50 text-status-success'
                      : 'text-label text-muted-foreground'
                  }
                >
                  {entry.status === 'done' ? '已播' : '略過'}
                </Badge>
              </TableCell>
              <TableCell className="hidden sm:table-cell text-right text-muted-foreground text-label tabular-nums">
                {entry.ended_at ? formatRelativeTime(entry.ended_at) : '—'}
              </TableCell>
              <TableCell className="text-right whitespace-nowrap">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="重新點播"
                      onClick={() => onRequeue(entry)}
                    >
                      <Icon icon="fa-solid fa-rotate-left" className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">重新點播</TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="封鎖"
                      onClick={() => onBlock(entry)}
                    >
                      <Icon icon="fa-solid fa-ban" className="size-3.5" />
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent side="left">加入封鎖清單</TooltipContent>
                </Tooltip>
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </TableShell>
  )
}
