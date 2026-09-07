import type { VideoQueueHistoryEntry } from '@/api/videoQueue'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Table,
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

import { SourceBadge } from './QueueTable'
import { formatDuration } from './utils'

const PLATFORM_LABEL: Record<string, string> = {
  twitch_clip: 'Clip',
  bilibili: 'Bilibili',
}

export function HistoryTable({
  entries,
  hasMore,
  loadingMore,
  onLoadMore,
  onRequeue,
}: {
  entries: VideoQueueHistoryEntry[]
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
  onRequeue: (entry: VideoQueueHistoryEntry) => void
}) {
  if (entries.length === 0) {
    return (
      <EmptyState
        icon="fa-solid fa-clock-rotate-left"
        title="尚無播放紀錄"
        description="播放或略過的影片會保留 30 天"
      />
    )
  }

  return (
    <div className="flex flex-col gap-element">
      <div className="overflow-x-auto">
        <Table className="table-fixed">
          <TableHeader>
            <TableRow>
              <TableHead>影片</TableHead>
              <TableHead className="w-20 sm:w-28">點播者</TableHead>
              <TableHead className="hidden sm:table-cell w-16 text-center">來源</TableHead>
              <TableHead className="w-16 text-center">狀態</TableHead>
              <TableHead className="hidden sm:table-cell w-20 text-right tabular-nums">
                時間
              </TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {entries.map(entry => (
              <TableRow key={entry.id}>
                <TableCell>
                  <div className="flex items-center gap-1.5 min-w-0">
                    {PLATFORM_LABEL[entry.video_type] && (
                      <Badge variant="outline" className="shrink-0 text-label px-1 py-0">
                        {PLATFORM_LABEL[entry.video_type]}
                      </Badge>
                    )}
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
                  {entry.duration_seconds ? ` · ${formatDuration(entry.duration_seconds)}` : ''}
                </TableCell>
                <TableCell className="text-right">
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
                    <TooltipContent>重新點播</TooltipContent>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {hasMore && (
        <Button
          variant="outline"
          size="sm"
          className="self-center"
          onClick={onLoadMore}
          disabled={loadingMore}
        >
          {loadingMore && <Spinner className="mr-1.5" />}
          載入更多
        </Button>
      )}
    </div>
  )
}
