import type { VideoQueueEntry } from '@/api/videoQueue'
import { Icon } from '@/components/primitives'
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

import { formatDuration } from './utils'

const SOURCE_CONFIG: Record<string, { label: string; className: string }> = {
  chat: { label: '聊天', className: 'text-muted-foreground' },
  redemption: {
    label: '兌換',
    className: 'border-status-special/50 text-status-special',
  },
  donation: {
    label: '斗內',
    className: 'border-status-warning/50 text-status-warning',
  },
  dashboard: {
    label: '主播',
    className: 'border-status-info/50 text-status-info',
  },
}

function ClipBadge() {
  return (
    <Badge
      variant="outline"
      className="shrink-0 text-label px-1 py-0 text-status-special border-status-special/60"
    >
      Clip
    </Badge>
  )
}

export function SourceBadge({ source }: { source: string }) {
  const cfg = SOURCE_CONFIG[source] ?? { label: source, className: '' }
  return (
    <Badge variant="outline" className={`shrink-0 text-label ${cfg.className}`}>
      {cfg.label}
    </Badge>
  )
}

export function QueueTable({
  current,
  entries,
  onSkip,
  onSetNext,
  onPlayNow,
  onRemove,
}: {
  current?: VideoQueueEntry | null
  entries: VideoQueueEntry[]
  onSkip?: () => void
  onSetNext?: (id: number) => void
  onPlayNow?: (id: number) => void
  onRemove?: (id: number) => void
}) {
  const hasActions = !!(onSetNext || onPlayNow || onRemove)
  if (!current && entries.length === 0) return null

  return (
    <div className="overflow-x-auto">
      {/* table-fixed: column widths are enforced by <th> — dynamic content can't shift fixed cols */}
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-10" />
            <TableHead>影片</TableHead>
            <TableHead className="w-20 sm:w-28">點播者</TableHead>
            <TableHead className="hidden sm:table-cell w-20 text-center">來源</TableHead>
            <TableHead className="w-16 tabular-nums">長度</TableHead>
            {(hasActions || onSkip) && <TableHead className="w-28" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {current && (
            <TableRow className="bg-primary/10">
              <TableCell>
                <Icon
                  icon="fa-solid fa-play"
                  className="size-3 text-primary"
                  wrapperClassName="mx-auto"
                />
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-1.5 min-w-0">
                  {current.video_type === 'twitch_clip' && <ClipBadge />}
                  <div className="truncate font-medium" title={current.title || current.video_id}>
                    {current.title || current.video_id}
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-muted-foreground text-sub">
                <span className="block truncate">{current.requested_by}</span>
              </TableCell>
              <TableCell className="hidden sm:table-cell text-center">
                <SourceBadge source={current.source} />
              </TableCell>
              <TableCell className="text-muted-foreground text-sub tabular-nums">
                {current.duration_seconds ? formatDuration(current.duration_seconds) : '--:--'}
              </TableCell>
              {(hasActions || onSkip) && (
                <TableCell className="text-right">
                  {onSkip && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon-sm" onClick={onSkip}>
                          <Icon icon="fa-solid fa-forward-step" className="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent>跳過當前影片</TooltipContent>
                    </Tooltip>
                  )}
                </TableCell>
              )}
            </TableRow>
          )}

          {entries.map((entry, idx) => (
            <TableRow key={entry.id}>
              <TableCell className="text-center">
                <Badge variant="outline">{idx + 1}</Badge>
              </TableCell>
              <TableCell>
                <div className="flex items-center gap-1.5 min-w-0">
                  {entry.video_type === 'twitch_clip' && <ClipBadge />}
                  <div className="truncate font-medium" title={entry.title || entry.video_id}>
                    {entry.title || entry.video_id}
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-muted-foreground text-sub">
                <span className="block truncate">{entry.requested_by}</span>
              </TableCell>
              <TableCell className="hidden sm:table-cell text-center">
                <SourceBadge source={entry.source} />
              </TableCell>
              <TableCell className="text-muted-foreground text-sub tabular-nums">
                {entry.duration_seconds ? formatDuration(entry.duration_seconds) : '--:--'}
              </TableCell>
              {(hasActions || onSkip) && (
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    {onSetNext && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => onSetNext(entry.id)}
                          >
                            <Icon icon="fa-solid fa-arrow-up-to-line" className="size-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>排定為下一首</TooltipContent>
                      </Tooltip>
                    )}
                    {onPlayNow && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => onPlayNow(entry.id)}
                          >
                            <Icon icon="fa-solid fa-play" className="size-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>直接插播</TooltipContent>
                      </Tooltip>
                    )}
                    {onRemove && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            onClick={() => onRemove(entry.id)}
                            className="border border-destructive/30 text-muted-foreground hover:border-destructive/60 hover:text-destructive"
                          >
                            <Icon icon="fa-solid fa-xmark" className="size-3.5" />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>移除</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
