import { useCallback, useEffect, useRef, useState } from 'react'

import {
  type BlocklistKind,
  getVideoQueueRankings,
  type VideoQueueRankingEntry,
  type VideoQueueRankingScope,
  type VideoType,
} from '@/api/videoQueue'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui'

import { PlatformBadge } from './QueueTable'
import { thumbnailUrl, watchUrl } from './utils'

const PROVIDERS: { value: VideoType | 'all'; label: string }[] = [
  { value: 'all', label: '所有平台' },
  { value: 'youtube', label: 'YouTube' },
  { value: 'twitch_clip', label: 'Twitch Clip' },
  { value: 'twitch_vod', label: 'Twitch VOD' },
  { value: 'bilibili', label: 'Bilibili' },
  { value: 'instagram_reel', label: 'Instagram' },
]

type PendingBlock = {
  entry: VideoQueueRankingEntry
  kind: Extract<BlocklistKind, 'video' | 'creator'>
}

export function RankingPanel({
  onAdd,
  onBlock,
}: {
  onAdd: (entry: VideoQueueRankingEntry) => Promise<void>
  onBlock: (
    entry: VideoQueueRankingEntry,
    kind: Extract<BlocklistKind, 'video' | 'creator'>
  ) => Promise<void>
}) {
  const [scope, setScope] = useState<VideoQueueRankingScope>('channel')
  const [days, setDays] = useState<7 | 30>(7)
  const [provider, setProvider] = useState<VideoType | 'all'>('all')
  const [entries, setEntries] = useState<VideoQueueRankingEntry[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [addingId, setAddingId] = useState<string | null>(null)
  const [pendingBlock, setPendingBlock] = useState<PendingBlock | null>(null)
  const requestId = useRef(0)

  const load = useCallback(
    async (
      nextScope: VideoQueueRankingScope,
      nextDays: 7 | 30,
      nextProvider: VideoType | 'all'
    ) => {
      const id = ++requestId.current
      setStatus('loading')
      try {
        const result = await getVideoQueueRankings(
          nextScope,
          nextDays,
          nextProvider === 'all' ? undefined : nextProvider
        )
        if (id !== requestId.current) return
        setEntries(result)
        setStatus('ready')
      } catch {
        if (id === requestId.current) setStatus('error')
      }
    },
    []
  )

  useEffect(() => {
    const requestSequence = requestId
    const timeoutId = window.setTimeout(() => void load('channel', 7, 'all'), 0)
    return () => {
      window.clearTimeout(timeoutId)
      requestSequence.current++
    }
  }, [load])

  const chooseScope = (next: VideoQueueRankingScope) => {
    setScope(next)
    void load(next, days, provider)
  }

  const chooseDays = (next: 7 | 30) => {
    setDays(next)
    void load(scope, next, provider)
  }

  const handleAdd = async (entry: VideoQueueRankingEntry) => {
    const key = `${entry.video_type}:${entry.video_id}`
    setAddingId(key)
    try {
      await onAdd(entry)
      setEntries(current =>
        current.map(item =>
          item.video_type === entry.video_type && item.video_id === entry.video_id
            ? { ...item, active_status: 'queued' }
            : item
        )
      )
    } catch {
      // Parent owns the user-facing error toast.
    } finally {
      setAddingId(null)
    }
  }

  const confirmBlock = async () => {
    if (!pendingBlock) return
    const { entry, kind } = pendingBlock
    setPendingBlock(null)
    try {
      await onBlock(entry, kind)
      setEntries(current =>
        current.map(item => {
          const matches =
            item.video_type === entry.video_type &&
            (kind === 'creator'
              ? !!entry.creator_id && item.creator_id === entry.creator_id
              : item.video_id === entry.video_id)
          return matches ? { ...item, blocked_kind: kind } : item
        })
      )
    } catch {
      // Parent owns the user-facing error toast.
    }
  }

  return (
    <div className="flex min-h-120 flex-1 flex-col gap-card">
      <div className="flex flex-wrap items-center justify-between gap-element">
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex rounded-md border border-border p-0.5" aria-label="排行範圍">
            {(['channel', 'global'] as const).map(value => (
              <Button
                key={value}
                size="sm"
                variant={scope === value ? 'secondary' : 'ghost'}
                onClick={() => chooseScope(value)}
              >
                {value === 'channel' ? '本台' : '全站'}
              </Button>
            ))}
          </div>
          <div className="flex rounded-md border border-border p-0.5" aria-label="排行期間">
            {([7, 30] as const).map(value => (
              <Button
                key={value}
                size="sm"
                variant={days === value ? 'secondary' : 'ghost'}
                onClick={() => chooseDays(value)}
              >
                {value} 日
              </Button>
            ))}
          </div>
        </div>
        <Select
          value={provider}
          onValueChange={value => {
            const next = value as VideoType | 'all'
            setProvider(next)
            void load(scope, days, next)
          }}
        >
          <SelectTrigger className="w-36" aria-label="影片平台">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PROVIDERS.map(item => (
              <SelectItem key={item.value} value={item.value}>
                {item.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <p className="text-label text-muted-foreground">
        {scope === 'global'
          ? '依使用頻道數與播放次數排序，只顯示匿名彙總，不公開頻道或點播者。'
          : '依本頻道的有效播放次數排序；播放器實際開始後才會計入。'}
      </p>

      {status === 'loading' ? (
        <div className="py-element">
          <TableSkeletonRows count={6} />
        </div>
      ) : status === 'error' ? (
        <div className="my-auto flex flex-col items-center gap-element">
          <EmptyState
            icon="fa-solid fa-chart-line"
            title="排行暫時載入失敗"
            description="請檢查連線後再試一次"
          />
          <Button size="sm" variant="outline" onClick={() => void load(scope, days, provider)}>
            重新載入
          </Button>
        </div>
      ) : entries.length === 0 ? (
        <EmptyState
          className="my-auto"
          icon="fa-solid fa-ranking-star"
          title="這段期間還沒有有效播放紀錄"
          description="影片由播放器開始播放後，才會出現在這裡"
        />
      ) : (
        <ol className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          {entries.map(entry => {
            const key = `${entry.video_type}:${entry.video_id}`
            const image = entry.thumbnail_url ?? thumbnailUrl(entry.video_type, entry.video_id)
            const actionLabel = entry.blocked_kind
              ? '已封鎖'
              : entry.active_status === 'playing'
                ? '播放中'
                : entry.active_status === 'queued'
                  ? '已在待播'
                  : '加入待播'
            return (
              <li
                key={key}
                className="flex min-w-0 flex-wrap items-center gap-3 rounded-lg border border-border/70 bg-card/40 p-3 sm:flex-nowrap"
              >
                <span className="w-7 shrink-0 text-center text-lg font-semibold tabular-nums text-muted-foreground">
                  {entry.rank}
                </span>
                <div className="relative h-14 w-24 shrink-0 overflow-hidden rounded-md bg-muted">
                  {image ? (
                    <img
                      src={image}
                      alt=""
                      className="size-full object-cover"
                      loading="lazy"
                      referrerPolicy="no-referrer"
                    />
                  ) : (
                    <Icon
                      icon="fa-solid fa-video"
                      className="text-muted-foreground"
                      wrapperClassName="flex size-full items-center justify-center"
                    />
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-1.5">
                    <PlatformBadge videoType={entry.video_type} />
                    <p
                      className="truncate text-sub font-medium"
                      title={entry.title ?? entry.video_id}
                    >
                      {entry.title ?? entry.video_id}
                    </p>
                  </div>
                  <p className="truncate text-label text-muted-foreground">
                    {entry.creator_name ?? entry.creator_id ?? '未知創作者'}
                  </p>
                  <p className="mt-1 text-label text-muted-foreground tabular-nums">
                    {scope === 'global'
                      ? `${entry.channel_count} 個頻道 · 播放 ${entry.play_count} 次`
                      : `播放 ${entry.play_count} 次`}
                  </p>
                </div>
                <div className="ml-auto flex w-full shrink-0 items-center justify-end gap-1 sm:w-auto">
                  <Button
                    size="sm"
                    onClick={() => void handleAdd(entry)}
                    disabled={!!entry.active_status || !!entry.blocked_kind || addingId === key}
                  >
                    {addingId === key && <Spinner className="mr-1.5" />}
                    {actionLabel}
                  </Button>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon-sm" aria-label="更多操作">
                        <Icon icon="fa-solid fa-ellipsis-vertical" className="size-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem asChild>
                        <a
                          href={watchUrl(entry.video_type, entry.video_id, entry.start_seconds)}
                          target="_blank"
                          rel="noreferrer"
                        >
                          開啟原始影片
                        </a>
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={entry.blocked_kind === 'video'}
                        onClick={() => setPendingBlock({ entry, kind: 'video' })}
                      >
                        封鎖此影片
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={!entry.creator_id || entry.blocked_kind === 'creator'}
                        onClick={() => setPendingBlock({ entry, kind: 'creator' })}
                      >
                        封鎖此創作者
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </li>
            )
          })}
        </ol>
      )}

      <DeleteConfirmDialog
        open={pendingBlock !== null}
        onOpenChange={open => !open && setPendingBlock(null)}
        title={pendingBlock?.kind === 'creator' ? '在此頻道封鎖創作者？' : '在此頻道封鎖影片？'}
        description="這個規則只套用目前頻道，並會依影片平台區分。"
        actionLabel={pendingBlock?.kind === 'creator' ? '封鎖創作者' : '封鎖影片'}
        onConfirm={() => void confirmBlock()}
      />
    </div>
  )
}
