import { type FormEvent, type ReactNode, useEffect, useState } from 'react'

import type { VideoQueueEntry, VideoQueueLiveInsert } from '@/api/videoQueue'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Progress,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'

import { PlatformBadge, SourceBadge } from './QueueTable'
import { formatDuration, liveWatchUrl, segmentLabel, thumbnailUrl, watchUrl } from './utils'

function Thumb({ entry, className }: { entry: VideoQueueEntry; className?: string }) {
  const [failed, setFailed] = useState(false)
  // Prefer the fetched poster (all platforms); fall back to YouTube's deterministic
  // thumbnail for older rows with no stored URL.
  const src = entry.thumbnail_url ?? thumbnailUrl(entry.video_type, entry.video_id)
  if (src && !failed) {
    return (
      <img
        src={src}
        alt=""
        loading="lazy"
        // Bilibili's image CDN 403s a cross-site Referer; send none.
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={`rounded-md border bg-muted object-cover ${className ?? ''}`}
      />
    )
  }
  return (
    <div
      className={`flex items-center justify-center rounded-md border bg-muted ${className ?? ''}`}
    >
      <Icon icon="fa-solid fa-circle-play" className="text-muted-foreground/40" />
    </div>
  )
}

/** The one place to put something on screen: queue a URL, or insert a live stream. */
export interface PlayComposer {
  url: string
  onUrlChange: (value: string) => void
  /** 影片 mode: add the URL to the queue. */
  onAdd: () => void
  /** 直播 mode: play the live stream now; the queue waits. */
  onPlayLive: () => void
  busy: 'add' | 'live' | null
}

type ComposerMode = 'video' | 'live'

const COMPOSER_MODES: Record<ComposerMode, { label: string; placeholder: string; icon: string }> = {
  video: {
    label: '影片網址',
    placeholder: '貼上影片網址，可加時間，例：1:30-4:00',
    icon: 'fa-solid fa-plus',
  },
  live: {
    label: '直播網址',
    placeholder: '貼上 Twitch 頻道或 YouTube 直播網址',
    icon: 'fa-solid fa-tower-broadcast',
  },
}

/**
 * The one place to put something on screen. The mode is chosen first so each
 * mode has exactly one action: a queue request and a live stream are
 * different things, and the backend rejects the wrong kind either way.
 */
function ComposerBar({ composer, liveActive }: { composer: PlayComposer; liveActive: boolean }) {
  const { url, onUrlChange, onAdd, onPlayLive, busy } = composer
  const [mode, setMode] = useState<ComposerMode>('video')
  const config = COMPOSER_MODES[mode]
  const empty = !url.trim()
  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (empty || busy) return
    if (mode === 'video') onAdd()
    else onPlayLive()
  }
  const actionLabel = mode === 'video' ? '加入' : liveActive ? '換台' : '播放直播'
  return (
    <form
      className="flex flex-col gap-element border-t pt-card sm:flex-row sm:items-center"
      onSubmit={submit}
    >
      <Tabs value={mode} onValueChange={value => setMode(value as ComposerMode)}>
        <TabsList aria-label="加入方式">
          <TabsTrigger value="video">影片</TabsTrigger>
          <TabsTrigger value="live">直播</TabsTrigger>
        </TabsList>
      </Tabs>
      <div className="flex flex-1 items-center gap-element">
        <div className="relative flex-1">
          <Icon
            icon="fa-solid fa-link"
            className="text-sub text-muted-foreground"
            wrapperClassName="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
          />
          <Input
            aria-label={config.label}
            placeholder={config.placeholder}
            value={url}
            onChange={event => onUrlChange(event.target.value)}
            className="pl-8"
          />
        </div>
        <Button type="submit" disabled={empty || busy !== null}>
          {busy ? (
            <Spinner className="mr-1.5" />
          ) : (
            <Icon icon={config.icon} wrapperClassName="mr-1.5 size-3" />
          )}
          {actionLabel}
        </Button>
      </div>
    </form>
  )
}

function OpenLink({ href, label }: { href: string; label: string }) {
  return (
    <Button size="icon-sm" variant="ghost" asChild title={label}>
      <a href={href} target="_blank" rel="noreferrer">
        <Icon icon="fa-solid fa-arrow-up-right-from-square" className="size-3" />
        <span className="sr-only">{label}</span>
      </a>
    </Button>
  )
}

export function NowPlayingCard({
  current,
  next,
  queueSize,
  totalQueuedDuration,
  onSkip,
  insert = null,
  onStopInsert,
  composer,
}: {
  current: VideoQueueEntry | null
  next?: VideoQueueEntry
  queueSize: number
  totalQueuedDuration: number | null
  onSkip: () => void
  /** Active live insert — shown instead of `current` (the queue is paused). */
  insert?: VideoQueueLiveInsert | null
  onStopInsert?: () => void
  composer?: PlayComposer
}) {
  const [now, setNow] = useState(() => Date.now())
  const startedAt = insert ? null : current?.started_at
  useEffect(() => {
    if (!startedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [startedAt])

  const upNext = (
    <div className="flex min-w-0 flex-col gap-element border-t pt-card lg:w-80 lg:border-t-0 lg:border-l lg:pt-0 lg:pl-card">
      <p className="text-label font-medium text-muted-foreground">
        {insert ? '直播結束後' : '接下來'}
      </p>
      {next ? (
        <div className="flex items-center gap-element min-w-0">
          <Thumb key={next.video_id} entry={next} className="aspect-video w-16 shrink-0" />
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

  let badge: ReactNode = null
  let action: ReactNode = null
  let body: ReactNode

  if (insert) {
    badge = (
      <Badge variant="outline" className="text-label border-status-live/60 text-status-live">
        LIVE
      </Badge>
    )
    action = (
      <>
        <OpenLink href={liveWatchUrl(insert)} label="開啟直播" />
        <Button size="sm" variant="outline" onClick={onStopInsert}>
          <Icon icon="fa-solid fa-stop" className="mr-1.5 size-3" />
          結束直播
        </Button>
      </>
    )
    body = (
      <div className="flex flex-col gap-card lg:flex-row">
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-element">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="shrink-0 text-label text-muted-foreground">
              {insert.source_type === 'twitch_live' ? 'Twitch' : 'YouTube'}
            </span>
            <span className="truncate text-content font-semibold">
              {insert.creator_name || insert.source_id}
            </span>
          </div>
          {insert.title && (
            <span className="truncate text-sub text-muted-foreground" title={insert.title}>
              {insert.title}
            </span>
          )}
          <span className="text-label text-muted-foreground">
            直播播放中，佇列暫停{insert.audio_only ? ' · 僅聲音' : ''}
          </span>
        </div>
        {upNext}
      </div>
    )
  } else if (current) {
    const elapsed = current.started_at
      ? Math.max(0, (now - new Date(current.started_at).getTime()) / 1000)
      : 0
    const duration = current.duration_seconds
    const progress = duration && duration > 0 ? Math.min(100, (elapsed / duration) * 100) : 0
    badge = (
      <Badge variant="secondary" className="text-label tabular-nums">
        {formatDuration(elapsed)} / {duration ? formatDuration(duration) : '--:--'}
      </Badge>
    )
    action = (
      <>
        <OpenLink
          href={watchUrl(current.video_type, current.video_id, current.start_seconds)}
          label="開啟影片"
        />
        <Button size="sm" variant="outline" onClick={onSkip}>
          <Icon icon="fa-solid fa-forward-step" className="mr-1.5 size-3" />
          跳過
        </Button>
      </>
    )
    body = (
      <div className="flex flex-col gap-card lg:flex-row">
        <div className="flex flex-1 gap-card min-w-0">
          <Thumb
            key={current.video_id}
            entry={current}
            className="aspect-video w-32 shrink-0 sm:w-44"
          />
          <div className="flex min-w-0 flex-1 flex-col justify-center gap-element">
            <div className="flex items-center gap-1.5 min-w-0">
              <PlatformBadge videoType={current.video_type} />
              <span
                className="truncate text-content font-semibold"
                title={current.title || current.video_id}
              >
                {current.title || current.video_id}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-sub text-muted-foreground min-w-0">
              <span className="truncate">{current.requested_by}</span>
              <SourceBadge source={current.source} />
              {segmentLabel(current) && (
                <span className="shrink-0 text-label tabular-nums">
                  片段 {segmentLabel(current)}
                </span>
              )}
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
      </div>
    )
  } else {
    body = (
      <EmptyState
        icon="fa-solid fa-circle-play"
        title="目前沒有播放"
        description={queueSize > 0 ? '佇列裡有影片，馬上就會開始' : '貼上連結，或等觀眾點播'}
      />
    )
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          現在播放
          {badge}
        </CardTitle>
        {action && <CardAction className="flex items-center gap-1">{action}</CardAction>}
      </CardHeader>
      <CardContent className="flex flex-col gap-card">
        {body}
        {composer && <ComposerBar composer={composer} liveActive={insert !== null} />}
      </CardContent>
    </Card>
  )
}
