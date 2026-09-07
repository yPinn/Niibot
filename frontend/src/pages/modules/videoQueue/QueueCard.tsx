import { useState } from 'react'

import type { VideoQueueEntry, VideoQueueHistoryEntry } from '@/api/videoQueue'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { EmptyState, Icon, Spinner } from '@/components/primitives'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  Input,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'

import { HistoryTable } from './HistoryTable'
import { QueueTable } from './QueueTable'
import { formatDuration, QUEUE_PAGE_SIZE } from './utils'

export type QueueTab = 'queue' | 'history'
export type HistoryState = 'idle' | 'loading' | 'more' | 'ready'

function Pager({
  page,
  totalPages,
  canPrev,
  canNext,
  loading,
  onPrev,
  onNext,
}: {
  page: number
  totalPages?: number
  canPrev: boolean
  canNext: boolean
  loading?: boolean
  onPrev: () => void
  onNext: () => void
}) {
  return (
    <div className="mt-auto flex items-center justify-center gap-2 pt-element">
      <Button variant="ghost" size="sm" onClick={onPrev} disabled={!canPrev}>
        <Icon icon="fa-solid fa-chevron-left" wrapperClassName="mr-1.5 size-3" />
        上一頁
      </Button>
      <span className="text-label text-muted-foreground tabular-nums">
        {totalPages ? `第 ${page + 1} / ${totalPages} 頁` : `第 ${page + 1} 頁`}
      </span>
      <Button variant="ghost" size="sm" onClick={onNext} disabled={!canNext}>
        {loading ? (
          <Spinner className="mr-1.5" />
        ) : (
          <Icon icon="fa-solid fa-chevron-right" wrapperClassName="mr-1.5 size-3" />
        )}
        下一頁
      </Button>
    </div>
  )
}

export function QueueCard({
  tab,
  onTabChange,
  queue,
  queueSize,
  totalQueuedDuration,
  addUrlInput,
  onAddUrlChange,
  adding,
  onAdd,
  onClear,
  canClear,
  onSetNext,
  onPlayNow,
  onRemove,
  history,
  historyState,
  historyPage,
  historyCanPrev,
  historyCanNext,
  onHistoryPrev,
  onHistoryNext,
  onRequeue,
  onBlock,
}: {
  tab: QueueTab
  onTabChange: (tab: QueueTab) => void
  queue: VideoQueueEntry[]
  queueSize: number
  totalQueuedDuration: number | null
  addUrlInput: string
  onAddUrlChange: (value: string) => void
  adding: boolean
  onAdd: () => void
  onClear: () => void
  canClear: boolean
  onSetNext: (id: number) => void
  onPlayNow: (id: number) => void
  onRemove: (id: number) => void
  history: VideoQueueHistoryEntry[]
  historyState: HistoryState
  historyPage: number
  historyCanPrev: boolean
  historyCanNext: boolean
  onHistoryPrev: () => void
  onHistoryNext: () => void
  onRequeue: (entry: VideoQueueHistoryEntry) => void
  onBlock: (entry: VideoQueueHistoryEntry) => void
}) {
  const [confirmClear, setConfirmClear] = useState(false)
  const [queuePage, setQueuePage] = useState(0)

  const queueTotalPages = Math.max(1, Math.ceil(queue.length / QUEUE_PAGE_SIZE))
  // Derive the shown page — the queue can shrink under us (skip / remove) and
  // leave `queuePage` past the end; clamp at render instead of syncing state.
  const safeQueuePage = Math.min(queuePage, queueTotalPages - 1)

  const queueSlice = queue.slice(
    safeQueuePage * QUEUE_PAGE_SIZE,
    safeQueuePage * QUEUE_PAGE_SIZE + QUEUE_PAGE_SIZE
  )
  const historySlice = history.slice(
    historyPage * QUEUE_PAGE_SIZE,
    historyPage * QUEUE_PAGE_SIZE + QUEUE_PAGE_SIZE
  )

  return (
    <Card className="h-full">
      <CardHeader>
        <Tabs value={tab} onValueChange={v => onTabChange(v as QueueTab)}>
          <TabsList>
            <TabsTrigger value="queue">待播</TabsTrigger>
            <TabsTrigger value="history">紀錄</TabsTrigger>
          </TabsList>
        </Tabs>
        <CardAction>
          <div className="flex items-center gap-3">
            <span className="hidden text-sub text-muted-foreground tabular-nums sm:inline">
              待播 {queueSize} 首
              {totalQueuedDuration ? ` · ${formatDuration(totalQueuedDuration)}` : ''}
            </span>
            <Button
              size="sm"
              variant="destructive"
              onClick={() => setConfirmClear(true)}
              disabled={!canClear}
            >
              <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
              清空
            </Button>
          </div>
        </CardAction>
      </CardHeader>

      <CardContent className="flex min-h-120 flex-1 flex-col gap-card">
        {tab === 'queue' ? (
          <>
            <div className="flex items-center gap-element">
              <div className="relative flex-1">
                <Icon
                  icon="fa-solid fa-link"
                  className="text-sub text-muted-foreground"
                  wrapperClassName="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
                />
                <Input
                  aria-label="影片連結"
                  placeholder="貼上影片連結（YouTube／Twitch／Bilibili）"
                  value={addUrlInput}
                  onChange={e => onAddUrlChange(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && onAdd()}
                  className="pl-8"
                />
              </div>
              <Button size="sm" onClick={onAdd} disabled={adding || !addUrlInput.trim()}>
                {adding ? (
                  <Spinner className="mr-1.5" />
                ) : (
                  <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
                )}
                {adding ? '新增中' : '新增'}
              </Button>
            </div>

            {queue.length === 0 ? (
              <EmptyState
                className="my-auto"
                icon="fa-solid fa-list-ul"
                title="佇列是空的"
                description="貼上連結按 Enter，或等觀眾點播"
              />
            ) : (
              <>
                <QueueTable
                  entries={queueSlice}
                  startIndex={safeQueuePage * QUEUE_PAGE_SIZE}
                  onSetNext={onSetNext}
                  onPlayNow={onPlayNow}
                  onRemove={onRemove}
                />
                {queueTotalPages > 1 && (
                  <Pager
                    page={safeQueuePage}
                    totalPages={queueTotalPages}
                    canPrev={safeQueuePage > 0}
                    canNext={safeQueuePage < queueTotalPages - 1}
                    onPrev={() => setQueuePage(Math.max(0, safeQueuePage - 1))}
                    onNext={() => setQueuePage(Math.min(queueTotalPages - 1, safeQueuePage + 1))}
                  />
                )}
              </>
            )}
          </>
        ) : historyState === 'loading' ? (
          <TableSkeletonRows count={QUEUE_PAGE_SIZE} />
        ) : (
          <>
            <HistoryTable entries={historySlice} onRequeue={onRequeue} onBlock={onBlock} />
            {(historyCanPrev || historyCanNext) && (
              <Pager
                page={historyPage}
                canPrev={historyCanPrev}
                canNext={historyCanNext}
                loading={historyState === 'more'}
                onPrev={onHistoryPrev}
                onNext={onHistoryNext}
              />
            )}
          </>
        )}
      </CardContent>

      <DeleteConfirmDialog
        open={confirmClear}
        onOpenChange={setConfirmClear}
        title="清空待播佇列？"
        description="佇列裡的影片會全部移除，正在播放的不受影響。這個動作無法復原。"
        actionLabel="清空"
        onConfirm={() => {
          setConfirmClear(false)
          onClear()
        }}
      />
    </Card>
  )
}
