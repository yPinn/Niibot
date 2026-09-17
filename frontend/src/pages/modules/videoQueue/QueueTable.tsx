import type { VideoQueueEntry } from '@/api/videoQueue'
import { Icon } from '@/components/primitives'
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

const PLATFORM_BADGE_CONFIG: Record<string, { label: string; className: string }> = {
  twitch_clip: { label: 'Clip', className: 'text-status-special border-status-special/60' },
  bilibili: { label: 'Bilibili', className: 'text-status-info border-status-info/60' },
  instagram_reel: { label: 'Reel', className: 'text-status-follow border-status-follow/60' },
}

export function PlatformBadge({ videoType }: { videoType: string }) {
  const cfg = PLATFORM_BADGE_CONFIG[videoType]
  if (!cfg) return null
  return (
    <Badge variant="outline" className={`shrink-0 text-label px-1 py-0 ${cfg.className}`}>
      {cfg.label}
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
  entries,
  startIndex = 0,
  onSetNext,
  onPlayNow,
  onRemove,
}: {
  entries: VideoQueueEntry[]
  /** Position of the first row in the full queue (for page 2+ numbering). */
  startIndex?: number
  onSetNext?: (id: number) => void
  onPlayNow?: (id: number) => void
  onRemove?: (id: number) => void
}) {
  const hasActions = !!(onSetNext || onPlayNow || onRemove)
  if (entries.length === 0) return null

  return (
    <TableShell>
      {/* table-fixed: column widths are enforced by <th> — dynamic content can't shift fixed cols */}
      <TableHeader>
        <TableRow>
          <TableHead className="w-10 text-center">#</TableHead>
          <TableHead>影片</TableHead>
          <TableHead className="w-20 sm:w-28">點播者</TableHead>
          <TableHead className="hidden sm:table-cell w-20 text-center">來源</TableHead>
          <TableHead className="w-16 tabular-nums">長度</TableHead>
          {hasActions && <TableHead className="w-28" />}
        </TableRow>
      </TableHeader>
      <TableBody>
        {entries.map((entry, idx) => (
          <TableRow key={entry.id}>
            <TableCell className="text-center">
              <Badge variant="outline">{startIndex + idx + 1}</Badge>
            </TableCell>
            <TableCell>
              <div className="flex items-center gap-1.5 min-w-0">
                <PlatformBadge videoType={entry.video_type} />
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
            {hasActions && (
              <TableCell className="text-right">
                <div className="flex justify-end gap-1">
                  {onSetNext && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon-sm" onClick={() => onSetNext(entry.id)}>
                          <Icon icon="fa-solid fa-arrow-up-to-line" className="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="left">排到最前面</TooltipContent>
                    </Tooltip>
                  )}
                  {onPlayNow && (
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button variant="ghost" size="icon-sm" onClick={() => onPlayNow(entry.id)}>
                          <Icon icon="fa-solid fa-play" className="size-3.5" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="left">馬上播這部</TooltipContent>
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
                      <TooltipContent side="left">移除</TooltipContent>
                    </Tooltip>
                  )}
                </div>
              </TableCell>
            )}
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  )
}
