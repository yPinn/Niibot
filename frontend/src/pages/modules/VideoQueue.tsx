import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoToQueue,
  clearVideoQueue,
  getVideoQueueSettings,
  getVideoQueueState,
  playVideoNow,
  type PublicVideoQueueState,
  setVideoAsNext,
  skipCurrentVideo,
  updateVideoQueueSettings,
  type VideoQueueEntry,
  type VideoQueueSettings,
} from '@/api/videoQueue'
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
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Icon,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
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

const POLL_INTERVAL = 10_000

const ROLE_OPTIONS = [
  { value: 'everyone', label: '所有人' },
  { value: 'subscriber', label: '訂閱者' },
  { value: 'vip', label: 'VIP' },
  { value: 'moderator', label: '管理員' },
  { value: 'broadcaster', label: '台主' },
] as const

const MIN_VIEW_COUNT_OPTIONS = [
  { value: 0, label: '不限制' },
  { value: 500, label: '500+' },
  { value: 1_000, label: '1,000+' },
  { value: 5_000, label: '5,000+' },
  { value: 10_000, label: '10,000+' },
] as const

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function QueueTable({
  entries,
  onSetNext,
  onPlayNow,
}: {
  entries: VideoQueueEntry[]
  onSetNext?: (id: number) => void
  onPlayNow?: (id: number) => void
}) {
  if (entries.length === 0) return null
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-16">#</TableHead>
            <TableHead>影片</TableHead>
            <TableHead className="w-24">長度</TableHead>
            <TableHead className="w-28">點播者</TableHead>
            {(onSetNext || onPlayNow) && <TableHead className="w-36" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry, idx) => (
            <TableRow key={entry.id}>
              <TableCell>
                <Badge variant="outline">{idx + 1}</Badge>
              </TableCell>
              <TableCell className="max-w-xs truncate font-medium">
                {entry.title || entry.video_id}
              </TableCell>
              <TableCell className="text-muted-foreground text-sub">
                {entry.duration_seconds ? formatDuration(entry.duration_seconds) : '--:--'}
              </TableCell>
              <TableCell className="text-muted-foreground text-sub">{entry.requested_by}</TableCell>
              {(onSetNext || onPlayNow) && (
                <TableCell className="text-right">
                  <div className="flex justify-end gap-1">
                    {onSetNext && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetNext(entry.id)}
                        title="排定為下一首"
                      >
                        <Icon icon="fa-solid fa-arrow-up-to-line" className="mr-1 size-3.5" />
                        下一首
                      </Button>
                    )}
                    {onPlayNow && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onPlayNow(entry.id)}
                        title="直接插播"
                      >
                        <Icon icon="fa-solid fa-play" className="mr-1 size-3.5" />
                        插播
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

export default function VideoQueue() {
  useDocumentTitle('Video Queue')

  const { user } = useAuth()
  const [state, setState] = useState<PublicVideoQueueState | null>(null)
  const [settings, setSettings] = useState<VideoQueueSettings | null>(null)
  const [loading, setLoading] = useState(true)

  const [maxDurationInput, setMaxDurationInput] = useState('')
  const [maxQueueSizeInput, setMaxQueueSizeInput] = useState('')
  const [userCooldownInput, setUserCooldownInput] = useState('')
  const [maxPerUserInput, setMaxPerUserInput] = useState('')
  const [saving, setSaving] = useState(false)

  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [addUrlInput, setAddUrlInput] = useState('')
  const [adding, setAdding] = useState(false)
  const hasInitialized = useRef(false)

  const fetchData = useCallback(async () => {
    try {
      const [queueState, queueSettings] = await Promise.all([
        getVideoQueueState(),
        getVideoQueueSettings(),
      ])
      setState(queueState)
      setSettings(queueSettings)
      if (!hasInitialized.current) {
        setMaxDurationInput(String(queueSettings.max_duration_seconds))
        setMaxQueueSizeInput(String(queueSettings.max_queue_size))
        setUserCooldownInput(String(queueSettings.user_cooldown_seconds))
        setMaxPerUserInput(String(queueSettings.max_per_user))
        hasInitialized.current = true
      }
    } catch {
      // silent on poll errors
    } finally {
      setLoading(false)
    }
  }, [])

  usePolling({ fetchFn: fetchData, intervalMs: POLL_INTERVAL })

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ enabled })
      setSettings(updated)
      toast.success(enabled ? '點播已開啟' : '點播已關閉')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleToggleChatEnabled = async (chat_enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ chat_enabled })
      setSettings(updated)
      toast.success(chat_enabled ? '!vq 指令已開啟' : '!vq 指令已關閉')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleToggleRedemptionEnabled = async (redemption_enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ redemption_enabled })
      setSettings(updated)
      toast.success(redemption_enabled ? '點數兌換已開啟' : '點數兌換已關閉')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleRoleChange = async (role: string) => {
    try {
      const updated = await updateVideoQueueSettings({ min_role_chat: role })
      setSettings(updated)
      toast.success('已更新最低權限')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleMinViewCountChange = async (value: string) => {
    try {
      const updated = await updateVideoQueueSettings({ min_view_count: Number(value) })
      setSettings(updated)
      toast.success('已更新最低觀看次數')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleSaveSettings = async () => {
    const duration = parseInt(maxDurationInput, 10)
    const queueSize = parseInt(maxQueueSizeInput, 10)
    const cooldown = parseInt(userCooldownInput, 10)
    const perUser = parseInt(maxPerUserInput, 10)
    if (isNaN(duration) || duration < 30 || duration > 10800) {
      toast.error('影片長度上限範圍: 30 ~ 10800 秒')
      return
    }
    if (isNaN(queueSize) || queueSize < 1 || queueSize > 100) {
      toast.error('隊列上限範圍: 1 ~ 100')
      return
    }
    if (isNaN(cooldown) || cooldown < 0 || cooldown > 3600) {
      toast.error('點歌冷卻時間範圍: 0 ~ 3600 秒')
      return
    }
    if (isNaN(perUser) || perUser < 0 || perUser > 20) {
      toast.error('每人上限範圍: 0 ~ 20（0 為不限制）')
      return
    }
    setSaving(true)
    try {
      const updated = await updateVideoQueueSettings({
        max_duration_seconds: duration,
        max_queue_size: queueSize,
        user_cooldown_seconds: cooldown,
        max_per_user: perUser,
      })
      setSettings(updated)
      toast.success('設定已儲存')
    } catch {
      toast.error('更新失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = async () => {
    try {
      const newState = await skipCurrentVideo()
      setState(newState)
      toast.success('已跳過當前影片')
    } catch {
      toast.error('跳過失敗')
    }
  }

  const handleClear = async () => {
    try {
      const newState = await clearVideoQueue()
      setState(newState)
      toast.success('已清空隊列')
    } catch {
      toast.error('清空失敗')
    }
  }

  const handleSetNext = async (entryId: number) => {
    try {
      const newState = await setVideoAsNext(entryId)
      setState(newState)
      toast.success('已移至下一首')
    } catch {
      toast.error('排序失敗')
    }
  }

  const handlePlayNow = async (entryId: number) => {
    try {
      const newState = await playVideoNow(entryId)
      setState(newState)
      toast.success('已插播')
    } catch {
      toast.error('插播失敗')
    }
  }

  const handleAddVideo = async () => {
    if (!addUrlInput.trim()) return
    setAdding(true)
    try {
      const newState = await addVideoToQueue(addUrlInput.trim())
      setState(newState)
      setAddUrlInput('')
      toast.success('已加入隊列')
    } catch (e) {
      toast.error(e instanceof Error ? e.message : '新增失敗')
    } finally {
      setAdding(false)
    }
  }

  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/video-queue/overlay` : ''

  if (loading) {
    return (
      <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
        <PageHeader title="Video Queue" description="管理 YouTube 點播系統" />
        <div className="flex items-center justify-center py-empty">
          <Spinner className="size-8 text-primary" />
        </div>
      </main>
    )
  }

  const current = state?.current ?? null
  const queue = state?.queue ?? []
  const queueSize = state?.queue_size ?? 0
  const totalQueuedDuration = state?.total_queued_duration ?? null

  return (
    <main className="flex flex-1 flex-col gap-section p-page lg:p-page-lg">
      <PageHeader title="Video Queue" description="管理 YouTube 點播系統" />

      {/* Settings + Overlay Preview */}
      <div className="grid grid-cols-1 gap-section lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>點播設定</CardTitle>
            <CardDescription>調整點播規則與權限</CardDescription>
            <CardAction>
              <Switch
                id="vq-enabled"
                checked={settings?.enabled ?? false}
                onCheckedChange={handleToggleEnabled}
              />
            </CardAction>
          </CardHeader>
          <CardContent className="space-y-5">
            {/* ── 來源開關 ── */}
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Switch
                  id="chat-enabled"
                  checked={settings?.chat_enabled ?? true}
                  onCheckedChange={handleToggleChatEnabled}
                />
                <Label htmlFor="chat-enabled" className="cursor-pointer">
                  !vq 指令
                </Label>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  id="redemption-enabled"
                  checked={settings?.redemption_enabled ?? true}
                  onCheckedChange={handleToggleRedemptionEnabled}
                />
                <Label htmlFor="redemption-enabled" className="cursor-pointer">
                  點數兌換
                </Label>
              </div>
            </div>

            <Separator />

            {/* ── 基本規則（2 欄）── */}
            <div className="grid grid-cols-2 gap-x-8 gap-y-3">
              <div className="flex items-center gap-3">
                <Label htmlFor="min-role" className="w-24 shrink-0">
                  最低點歌權限
                </Label>
                <Select
                  value={settings?.min_role_chat ?? 'everyone'}
                  onValueChange={handleRoleChange}
                >
                  <SelectTrigger id="min-role" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ROLE_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex items-center gap-3">
                <Label htmlFor="max-duration" className="w-24 shrink-0">
                  影片長度上限
                </Label>
                <Input
                  id="max-duration"
                  type="number"
                  min={30}
                  max={10800}
                  placeholder="600"
                  value={maxDurationInput}
                  onChange={e => setMaxDurationInput(e.target.value)}
                  className="w-20"
                />
                <span className="text-muted-foreground text-sub">秒</span>
              </div>

              <div className="flex items-center gap-3">
                <Label htmlFor="max-queue-size" className="w-24 shrink-0">
                  隊列上限
                </Label>
                <Input
                  id="max-queue-size"
                  type="number"
                  min={1}
                  max={100}
                  placeholder="20"
                  value={maxQueueSizeInput}
                  onChange={e => setMaxQueueSizeInput(e.target.value)}
                  className="w-20"
                />
                <span className="text-muted-foreground text-sub">首</span>
              </div>
            </div>

            {/* ── 進階設定（摺疊）── */}
            <Collapsible open={advancedOpen} onOpenChange={setAdvancedOpen}>
              <CollapsibleTrigger className="text-muted-foreground hover:text-foreground flex items-center gap-1.5 text-sm transition-colors">
                <Icon
                  icon="fa-solid fa-chevron-right"
                  className={`size-3 transition-transform duration-200 ${advancedOpen ? 'rotate-90' : ''}`}
                />
                進階設定
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="grid grid-cols-2 gap-x-8 gap-y-3 pt-3">
                  <div className="flex items-center gap-3">
                    <Label htmlFor="max-per-user" className="w-24 shrink-0">
                      每人同時上限
                    </Label>
                    <Input
                      id="max-per-user"
                      type="number"
                      min={0}
                      max={20}
                      placeholder="0"
                      value={maxPerUserInput}
                      onChange={e => setMaxPerUserInput(e.target.value)}
                      className="w-20"
                    />
                    <span className="text-muted-foreground text-sub">首</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <Label htmlFor="user-cooldown" className="w-24 shrink-0">
                      點歌冷卻
                    </Label>
                    <Input
                      id="user-cooldown"
                      type="number"
                      min={0}
                      max={3600}
                      placeholder="0"
                      value={userCooldownInput}
                      onChange={e => setUserCooldownInput(e.target.value)}
                      className="w-20"
                    />
                    <span className="text-muted-foreground text-sub">秒</span>
                  </div>

                  <div className="flex items-center gap-3">
                    <Label htmlFor="min-view-count" className="w-24 shrink-0">
                      最低觀看次數
                    </Label>
                    <Select
                      value={String(settings?.min_view_count ?? 0)}
                      onValueChange={handleMinViewCountChange}
                    >
                      <SelectTrigger id="min-view-count" className="w-32">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {MIN_VIEW_COUNT_OPTIONS.map(opt => (
                          <SelectItem key={opt.value} value={String(opt.value)}>
                            {opt.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </CollapsibleContent>
            </Collapsible>

            {/* ── 儲存 ── */}
            <div className="flex justify-end">
              <Button size="sm" onClick={handleSaveSettings} disabled={saving}>
                {saving ? '...' : '儲存'}
              </Button>
            </div>

            <Separator />

            <OverlayUrlBlock url={overlayUrl} />
          </CardContent>
        </Card>

        {overlayUrl && (
          <div className="aspect-16/10 overflow-hidden rounded-lg border bg-black">
            <iframe
              src={`${overlayUrl}?preview=1`}
              className="block h-full w-full"
              title="Overlay 預覽"
            />
          </div>
        )}
      </div>

      {/* Now Playing */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>
              正在播放
              {current && (
                <Badge variant="secondary" className="ml-2">
                  {current.duration_seconds ? formatDuration(current.duration_seconds) : 'LIVE'}
                </Badge>
              )}
            </CardTitle>
            {current && (
              <CardDescription>
                {current.title || current.video_id}
                <span className="text-muted-foreground ml-2">— by {current.requested_by}</span>
              </CardDescription>
            )}
            {!current && <CardDescription>目前沒有播放中的影片</CardDescription>}
          </div>
          <Button size="sm" onClick={handleSkip} disabled={!current}>
            <Icon icon="fa-solid fa-forward-step" className="mr-1.5 text-xs" />
            跳過
          </Button>
        </CardHeader>
      </Card>

      {/* Queue */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>
              等待隊列{' '}
              <Badge variant="outline">
                {queueSize}
                {totalQueuedDuration ? ` — ${formatDuration(totalQueuedDuration)}` : ''}
              </Badge>
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Input
              aria-label="YouTube 連結"
              placeholder="YouTube 連結"
              value={addUrlInput}
              onChange={e => setAddUrlInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleAddVideo()}
              className="w-56"
            />
            <Button size="sm" onClick={handleAddVideo} disabled={adding || !addUrlInput.trim()}>
              <Icon icon="fa-solid fa-plus" className="mr-1.5 text-xs" />
              {adding ? '...' : '新增'}
            </Button>
            <Button
              size="sm"
              variant="destructive"
              onClick={handleClear}
              disabled={queueSize === 0}
            >
              <Icon icon="fa-solid fa-trash" className="mr-1.5 text-xs" />
              清空
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <QueueTable entries={queue} onSetNext={handleSetNext} onPlayNow={handlePlayNow} />
          {queue.length === 0 && (
            <p className="text-muted-foreground text-sub py-4 text-center">隊列為空</p>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
