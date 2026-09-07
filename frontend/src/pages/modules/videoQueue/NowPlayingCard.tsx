import { useEffect, useState } from 'react'

import type { VideoQueueEntry } from '@/api/videoQueue'
import { EmptyState, Icon } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Progress,
} from '@/components/ui'

import { PlatformBadge, SourceBadge } from './QueueTable'
import { formatDuration, thumbnailUrl, watchUrl } from './utils'

function Thumb({ entry, className }: { entry: VideoQueueEntry; className?: string }) {
  const src = thumbnailUrl(entry.video_type, entry.video_id)
  if (src) {
    return <img src={src} alt="" className={`rounded-md border object-cover ${className ?? ''}`} />
  }
  return (
    <div
      className={`flex items-center justify-center rounded-md border bg-muted ${className ?? ''}`}
    >
      <Icon icon="fa-solid fa-circle-play" className="text-muted-foreground/40" />
    </div>
  )
}

export function NowPlayingCard({
  current,
  next,
  queueSize,
  totalQueuedDuration,
  onSkip,
}: {
  current: VideoQueueEntry | null
  next?: VideoQueueEntry
  queueSize: number
  totalQueuedDuration: number | null
  onSkip: () => void
}) {
  const [now, setNow] = useState(() => Date.now())
  const startedAt = current?.started_at
  useEffect(() => {
    if (!startedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  const upNext = (
    <div className="flex min-w-0 flex-col gap-element border-t pt-card lg:w-80 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-card">
      <p className="text-label font-medium text-muted-foreground">接下來</p>
      {next ? (
        <div className="flex items-center gap-element min-w-0">
          <Thumb entry={next} className="aspect-video w-16 shrink-0" />
          <div className="flex min-w-0 flex-col">
            <span className="truncate text-sub font-medium" title={next.title || next.video_id}>
              {next.title || next.video_id}
            </span>
            <span className="truncate text-label text-muted-foreground">{next.requested_by}</span>
          </div>
        </div>
      ) : (
        <p className="text-sub text-muted-foreground">佇列中沒有其他影片</p>
      )}
      <p className="mt-auto text-label text-muted-foreground tabular-nums">
        {queueSize > 0
          ? `待播 ${queueSize} 首${totalQueuedDuration ? ` · 約 ${formatDuration(totalQueuedDuration)}` : ''}`
          : '待播佇列為空'}
      </p>
    </div>
  )

  if (!current) {
    return (
      <Card className="min-h-52 justify-center">
        <CardContent>
          <EmptyState
            icon="fa-solid fa-circle-play"
            title="目前沒有播放"
            description={
              queueSize > 0 ? '佇列裡有影片，馬上就會開始' : '貼上影片連結，或等觀眾用點數點播'
            }
          />
        </CardContent>
      </Card>
    )
  }

  const elapsed = current.started_at
    ? Math.max(0, (now - new Date(current.started_at).getTime()) / 1000)
    : 0
  const duration = current.duration_seconds
  const progress = duration && duration > 0 ? Math.min(100, (elapsed / duration) * 100) : 0

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          現在播放
          <Badge variant="secondary" className="text-label tabular-nums">
            {formatDuration(elapsed)} / {duration ? formatDuration(duration) : '--:--'}
          </Badge>
        </CardTitle>
        <CardAction className="flex items-center gap-1">
          <Button size="icon-sm" variant="ghost" asChild title="在新分頁開啟影片">
            <a
              href={watchUrl(current.video_type, current.video_id)}
              target="_blank"
              rel="noreferrer"
            >
              <Icon icon="fa-solid fa-arrow-up-right-from-square" className="size-3" />
              <span className="sr-only">在新分頁開啟影片</span>
            </a>
          </Button>
          <Button size="sm" variant="outline" onClick={onSkip}>
            <Icon icon="fa-solid fa-forward-step" className="mr-1.5 size-3" />
            跳過
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="flex flex-col gap-card lg:flex-row">
        <div className="flex flex-1 gap-card min-w-0">
          <Thumb entry={current} className="aspect-video w-32 shrink-0 sm:w-44" />
          <div className="flex min-w-0 flex-1 flex-col justify-center gap-element">
            <div className="flex items-center gap-1.5 min-w-0">
              <PlatformBadge videoType={current.video_type} />
              <span className="truncate font-medium" title={current.title || current.video_id}>
                {current.title || current.video_id}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-sub text-muted-foreground min-w-0">
              <span className="truncate">{current.requested_by}</span>
              <SourceBadge source={current.source} />
            </div>
            <div className="flex flex-col gap-1.5 pt-1">
              <Progress segments={[{ value: progress }]} aria-label="播放進度" />
              <span className="text-label text-muted-foreground tabular-nums">
                {duration
                  ? `還剩 ${formatDuration(Math.max(0, duration - elapsed))}`
                  : '影片長度未知'}
              </span>
            </div>
          </div>
        </div>
        {upNext}
      </CardContent>
    </Card>
  )
}
