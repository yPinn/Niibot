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
  onRemove,
  onPromote,
  showRemove = false,
  showPromote = false,
}: {
  entries: QueueEntry[]
  onRemove?: (id: number) => void
  onPromote?: (id: number) => void
  showRemove?: boolean
  showPromote?: boolean
}) {
  if (entries.length === 0) return null
  const hasActions = showRemove || showPromote
  return (
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
                <div className="flex justify-end gap-1">
                  {showPromote && onPromote && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onPromote(entry.id)}
                      title="移至當前"
                    >
                      <Icon icon="fa-solid fa-arrow-up-to-line" className="mr-1 size-3.5" />
                      移至當前
                    </Button>
                  )}
                  {showRemove && onRemove && (
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => onRemove(entry.id)}
                      className="h-7 w-7 p-0 text-destructive hover:text-destructive"
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
  )
}

export default function GameQueue() {
  useDocumentTitle('Game Queue')

  const { user } = useAuth()
  const [state, setState] = useState<QueueState | null>(null)
  const [loading, setLoading] = useState(true)
  const [groupSizeInput, setGroupSizeInput] = useState('')
  const [saving, setSaving] = useState(false)
  const hasInitialized = useRef(false)

  const fetchState = useCallback(async () => {
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
  }, [])

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

  // Build overlay URL
  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/game-queue/overlay` : ''

  if (loading) {
    return (
      <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
        <PageHeader title="Game Queue" description="管理遊戲排隊系統" />
        <div className="flex items-center justify-center py-empty">
          <Spinner className="size-8 text-primary" />
        </div>
      </main>
    )
  }

  return (
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <PageHeader title="Game Queue" description="管理遊戲排隊系統" />

      {/* Settings + Overlay Preview */}
      <div className="grid grid-cols-1 gap-section lg:grid-cols-3">
        <Card className="col-span-2">
          <CardHeader>
            <CardTitle>隊列設定</CardTitle>
            <CardDescription>調整每場人數</CardDescription>
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
                  從佇列取 {Math.max(1, state.group_size - 1)} 人
                </span>
              )}
            </div>
            <OverlayUrlBlock url={overlayUrl} />
          </CardContent>
        </Card>

        {overlayUrl && (
          <div className="overflow-hidden rounded-lg border bg-black">
            <iframe src={overlayUrl} className="block h-full w-full" title="Overlay 預覽" />
          </div>
        )}
      </div>

      {/* Current Batch */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>
              當前批次{' '}
              <Badge variant="secondary">
                {state?.current_batch.length ?? 0} / {Math.max(1, (state?.group_size ?? 1) - 1)}
              </Badge>
            </CardTitle>
          </div>
          <Button size="sm" onClick={handleAdvance} disabled={!state?.current_batch.length}>
            <Icon icon="fa-solid fa-forward-step" className="mr-1.5 text-xs" />
            下一批
          </Button>
        </CardHeader>
        <CardContent>
          <EntryTable entries={state?.current_batch ?? []} onRemove={handleRemove} showRemove />
        </CardContent>
      </Card>

      {/* Next Batch */}
      <Card>
        <CardHeader>
          <CardTitle>
            下一批次 <Badge variant="outline">{state?.next_batch.length ?? 0}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <EntryTable
            entries={state?.next_batch ?? []}
            onRemove={handleRemove}
            onPromote={handlePromote}
            showRemove
            showPromote
          />
        </CardContent>
      </Card>

      {/* Full Queue */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>
              完整隊列 <Badge variant="outline">{state?.total_active ?? 0}</Badge>
            </CardTitle>
          </div>
          <Button
            size="sm"
            variant="destructive"
            onClick={handleClear}
            disabled={!state?.total_active}
          >
            <Icon icon="fa-solid fa-trash" className="mr-1.5 text-xs" />
            清空
          </Button>
        </CardHeader>
        <CardContent>
          <EntryTable
            entries={state?.full_queue ?? []}
            onRemove={handleRemove}
            onPromote={handlePromote}
            showRemove
            showPromote
          />
        </CardContent>
      </Card>
    </main>
  )
}
