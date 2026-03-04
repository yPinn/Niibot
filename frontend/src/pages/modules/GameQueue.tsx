import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  advanceBatch,
  clearQueue,
  getQueueState,
  promotePlayer,
  type QueueEntry,
  type QueueState,
  removePlayer,
  updateQueueSettings,
} from '@/api/gameQueue'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Input,
  Label,
  Spinner,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { usePolling } from '@/hooks/usePolling'

const POLL_INTERVAL = 15_000

function formatTime(dateStr: string) {
  return new Date(dateStr).toLocaleTimeString('zh-TW', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

function EntryTable({
  entries,
  emptyText,
  onRemove,
  onPromote,
  showRemove = false,
  showPromote = false,
}: {
  entries: QueueEntry[]
  emptyText?: string
  onRemove?: (id: number) => void
  onPromote?: (id: number) => void
  showRemove?: boolean
  showPromote?: boolean
}) {
  const hasActions = showRemove || showPromote

  if (entries.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 text-muted-foreground">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 640 512"
          className="size-20 opacity-25"
          fill="currentColor"
          aria-hidden="true"
        >
          {/* Font Awesome users path */}
          <path d="M144 160A80 80 0 1 0 144 0a80 80 0 1 0 0 160zm368 0A80 80 0 1 0 512 0a80 80 0 1 0 0 160zM0 298.7C0 310.4 9.6 320 21.3 320l213.3 0c.2 0 .4 0 .7 0c-26.6-23.5-43.3-57.8-43.3-96c0-7.6 .7-15 1.9-22.3c-13.6-6.3-28.7-9.7-44.6-9.7l-42.7 0C47.8 192 0 239.8 0 298.7zM320 320a128 128 0 1 0 0-256 128 128 0 1 0 0 256zm45.3 32l-90.7 0C187.7 352 128 411.7 128 485.3c0 14.7 11.9 26.7 26.7 26.7l330.7 0c14.7 0 26.7-11.9 26.7-26.7C512 411.7 452.3 352 365.3 352zm143.4-128c-.3 0-.6 0-.7 0l0 .1c1.3 7.3 1.9 14.7 1.9 22.2c0 38.2-16.8 72.5-43.3 96l213.4 0c11.8 0 21.3-9.6 21.3-21.3C640 239.8 592.2 192 544 192l-42.7 0c-15.9 0-31 3.5-44.6 9.7z" />
        </svg>
        <div className="flex flex-col items-center gap-1">
          <span className="text-sm font-medium">{emptyText ?? '目前無玩家'}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-16">#</TableHead>
            <TableHead>玩家</TableHead>
            <TableHead className="w-24">加入時間</TableHead>
            {hasActions && <TableHead className="w-32" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map(entry => (
            <TableRow key={entry.id}>
              <TableCell>
                <Badge variant="outline">{entry.position}</Badge>
              </TableCell>
              <TableCell className="font-medium">{entry.user_name}</TableCell>
              <TableCell className="text-muted-foreground text-sub">
                {formatTime(entry.redeemed_at)}
              </TableCell>
              {hasActions && (
                <TableCell className="text-right">
                  <div className="flex items-center justify-end gap-1">
                    {showPromote && onPromote && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onPromote(entry.id)}
                        title="移至當前"
                      >
                        <Icon icon="fa-solid fa-arrow-up-to-line" wrapperClassName="size-3.5" />
                        移至當前
                      </Button>
                    )}
                    {showRemove && onRemove && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onRemove(entry.id)}
                        className="size-8 p-0 text-destructive hover:text-destructive"
                      >
                        <Icon icon="fa-solid fa-xmark" className="text-xs" />
                      </Button>
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

export default function GameQueue() {
  useDocumentTitle('Game Queue')

  const { user, isAffiliate } = useAuth()
  const [state, setState] = useState<QueueState | null>(null)
  const [loading, setLoading] = useState(true)
  const [groupSizeInput, setGroupSizeInput] = useState('')
  const [saving, setSaving] = useState(false)
  const hasInitialized = useRef(false)

  const fetchState = useCallback(async () => {
    if (!isAffiliate) {
      setLoading(false)
      return
    }
    try {
      const data = await getQueueState()
      setState(data)
      if (!hasInitialized.current) {
        setGroupSizeInput(String(data.group_size))
        hasInitialized.current = true
      }
    } catch {
      // silent on poll errors
    } finally {
      setLoading(false)
    }
  }, [isAffiliate])

  usePolling({ fetchFn: fetchState, intervalMs: POLL_INTERVAL })

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      await updateQueueSettings({ enabled })
      setState(prev => (prev ? { ...prev, enabled } : prev))
      toast.success(enabled ? '隊列已開啟' : '隊列已關閉')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleSaveGroupSize = async () => {
    const size = parseInt(groupSizeInput, 10)
    if (isNaN(size) || size < 1 || size > 20) {
      toast.error('人數範圍: 1-20')
      return
    }
    setSaving(true)
    try {
      await updateQueueSettings({ group_size: size })
      await fetchState()
      toast.success(`已調整為 ${size} 人/場`)
    } catch {
      toast.error('更新失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleAdvance = async () => {
    try {
      const newState = await advanceBatch()
      setState(newState)
      toast.success('已結算當前批次')
    } catch {
      toast.error('結算失敗')
    }
  }

  const handleRemove = async (entryId: number) => {
    try {
      const newState = await removePlayer(entryId)
      setState(newState)
    } catch {
      toast.error('移除失敗')
    }
  }

  const handlePromote = async (entryId: number) => {
    try {
      const newState = await promotePlayer(entryId)
      setState(newState)
      toast.success('已移至當前批次')
    } catch {
      toast.error('移至失敗')
    }
  }

  const handleClear = async () => {
    try {
      const result = await clearQueue()
      setState(result)
      toast.success(`已清空隊列 (${result.cleared_count} 人)`)
    } catch {
      toast.error('清空失敗')
    }
  }

  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/game-queue/overlay` : ''

  if (loading) {
    return (
      <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
        <PageHeader title="Game Queue" description="管理遊戲排隊系統" />
        <div className="flex items-center justify-center py-empty">
          <Spinner className="size-8 text-primary" />
        </div>
      </main>
    )
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Game Queue" description="管理遊戲排隊系統" />

      <div className="relative flex flex-1 flex-col gap-section">
        {/* Inline overlay for non-affiliates — blurs preview, blocks interaction */}
        {!isAffiliate && (
          <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-xl bg-background/70 backdrop-blur-sm">
            <Icon icon="fa-solid fa-lock" wrapperClassName="size-10 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">
              成為 Twitch 聯盟夥伴或合作夥伴後即可使用遊戲排隊功能
            </span>
          </div>
        )}

        {/* Row 1: Full Queue (col-8) + sidebar (col-4) */}
        <div className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch">
        {/* Full Queue card — fills full column height */}
        <div className="lg:col-span-8">
          <Card className="h-full min-h-[520px]">
            <CardHeader>
              <CardTitle>
                等待佇列
                <Badge variant="outline" className="ml-2">
                  {state?.total_active ?? 0}
                </Badge>
              </CardTitle>
              <CardAction>
                <div className="flex items-center gap-2">
                  <Button size="sm" onClick={handleAdvance} disabled={!state?.current_batch.length}>
                    <Icon icon="fa-solid fa-forward-step" className="mr-1.5 text-xs" />
                    下一批
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    onClick={handleClear}
                    disabled={!state?.total_active}
                  >
                    <Icon icon="fa-solid fa-trash" className="mr-1.5 text-xs" />
                    清空
                  </Button>
                </div>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col">
              <EntryTable
                entries={state?.full_queue ?? []}
                emptyText="目前佇列無玩家"
                onRemove={handleRemove}
                onPromote={handlePromote}
                showRemove
                showPromote
              />
            </CardContent>
          </Card>
        </div>

        {/* Right sidebar: Overlay preview + queue settings */}
        <div className="flex flex-col gap-section lg:col-span-4">
          {/* Overlay preview iframe — fills remaining sidebar height */}
          {overlayUrl && (
            <div className="min-h-0 flex-1 overflow-hidden rounded-lg border bg-black">
              <iframe
                src={`${overlayUrl}?preview=1`}
                className="block h-full w-full"
                title="Overlay 預覽"
              />
            </div>
          )}

          {/* Queue settings card */}
          <Card>
            <CardHeader>
              <CardTitle>隊列設定</CardTitle>
              <CardDescription>調整每場人數與開關</CardDescription>
              <CardAction>
                <Switch
                  id="queue-enabled"
                  checked={state?.enabled ?? false}
                  onCheckedChange={handleToggleEnabled}
                />
              </CardAction>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground text-sub shrink-0">快速預設</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setGroupSizeInput('5')}
                  className="h-7"
                >
                  LoL / Val (5人)
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setGroupSizeInput('3')}
                  className="h-7"
                >
                  Apex (3人)
                </Button>
              </div>
              <div className="flex items-center gap-3">
                <Label htmlFor="group-size" className="shrink-0">
                  每場人數（含台主）
                </Label>
                <Input
                  id="group-size"
                  type="number"
                  min={1}
                  max={20}
                  value={groupSizeInput}
                  onChange={e => setGroupSizeInput(e.target.value)}
                  className="w-20"
                />
                <Button size="sm" onClick={handleSaveGroupSize} disabled={saving}>
                  {saving ? '...' : '儲存'}
                </Button>
                {state && (
                  <span className="text-muted-foreground text-sub">
                    取 {Math.max(1, state.group_size - 1)} 人
                  </span>
                )}
              </div>
              <OverlayUrlBlock url={overlayUrl} />
            </CardContent>
          </Card>
        </div>
      </div>
      </div>
    </main>
  )
}
