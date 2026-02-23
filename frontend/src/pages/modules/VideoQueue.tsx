import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  clearVideoQueue,
  getVideoQueueSettings,
  getVideoQueueState,
  type PublicVideoQueueState,
  skipCurrentVideo,
  updateVideoQueueSettings,
  type VideoQueueEntry,
  type VideoQueueSettings,
} from '@/api/videoQueue'
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
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

const POLL_INTERVAL = 10_000

const ROLE_OPTIONS = [
  { value: 'everyone', label: '所有人' },
  { value: 'subscriber', label: '訂閱者' },
  { value: 'vip', label: 'VIP' },
  { value: 'moderator', label: '管理員' },
  { value: 'broadcaster', label: '台主' },
] as const

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function QueueTable({ entries }: { entries: VideoQueueEntry[] }) {
  if (entries.length === 0) return null
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-16">#</TableHead>
          <TableHead>影片</TableHead>
          <TableHead className="w-24">長度</TableHead>
          <TableHead className="w-28">點播者</TableHead>
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
          </TableRow>
        ))}
      </TableBody>
    </Table>
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
  const [saving, setSaving] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchData = useCallback(async () => {
    try {
      const [queueState, queueSettings] = await Promise.all([
        getVideoQueueState(),
        getVideoQueueSettings(),
      ])
      setState(queueState)
      setSettings(queueSettings)
      setMaxDurationInput(String(queueSettings.max_duration_seconds))
      setMaxQueueSizeInput(String(queueSettings.max_queue_size))
    } catch {
      // silent on poll errors
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    pollRef.current = setInterval(fetchData, POLL_INTERVAL)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [fetchData])

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ enabled })
      setSettings(updated)
      toast.success(enabled ? '點播已開啟' : '點播已關閉')
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

  const handleSaveSettings = async () => {
    const duration = parseInt(maxDurationInput, 10)
    const queueSize = parseInt(maxQueueSizeInput, 10)
    if (isNaN(duration) || duration < 30 || duration > 10800) {
      toast.error('影片長度上限範圍: 30 ~ 10800 秒')
      return
    }
    if (isNaN(queueSize) || queueSize < 1 || queueSize > 100) {
      toast.error('隊列上限範圍: 1 ~ 100')
      return
    }
    setSaving(true)
    try {
      const updated = await updateVideoQueueSettings({
        max_duration_seconds: duration,
        max_queue_size: queueSize,
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

  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/video-queue/overlay` : ''

  if (loading) {
    return (
      <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
        <div>
          <h1 className="text-page-title font-bold">Video Queue</h1>
          <p className="text-sub text-muted-foreground">管理 YouTube 點播系統</p>
        </div>
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
    <main className="flex flex-1 flex-col gap-section p-page md:p-page-lg">
      <div>
        <h1 className="text-page-title font-bold">Video Queue</h1>
        <p className="text-sub text-muted-foreground">管理 YouTube 點播系統</p>
      </div>

      {/* Settings */}
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
        <CardContent className="space-y-4">
          <div className="flex items-center gap-3">
            <Label htmlFor="min-role" className="shrink-0">
              最低權限
            </Label>
            <Select value={settings?.min_role_chat ?? 'everyone'} onValueChange={handleRoleChange}>
              <SelectTrigger className="w-36">
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
            <Label htmlFor="max-duration" className="shrink-0">
              影片長度上限 (秒)
            </Label>
            <Input
              id="max-duration"
              type="number"
              min={30}
              max={10800}
              value={maxDurationInput}
              onChange={e => setMaxDurationInput(e.target.value)}
              className="w-24"
            />
          </div>

          <div className="flex items-center gap-3">
            <Label htmlFor="max-queue-size" className="shrink-0">
              隊列上限
            </Label>
            <Input
              id="max-queue-size"
              type="number"
              min={1}
              max={100}
              value={maxQueueSizeInput}
              onChange={e => setMaxQueueSizeInput(e.target.value)}
              className="w-24"
            />
            <Button size="sm" onClick={handleSaveSettings} disabled={saving}>
              {saving ? '...' : '儲存'}
            </Button>
          </div>

          {overlayUrl && (
            <div className="flex items-center gap-3">
              <Label className="shrink-0">OBS Overlay</Label>
              <code className="flex-1 truncate rounded bg-muted px-2 py-1 text-label">
                {overlayUrl}
              </code>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(overlayUrl)
                  toast.success('已複製')
                }}
              >
                <Icon icon="fa-solid fa-copy" className="text-xs" />
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

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
          <Button size="sm" variant="destructive" onClick={handleClear} disabled={queueSize === 0}>
            <Icon icon="fa-solid fa-trash" className="mr-1.5 text-xs" />
            清空
          </Button>
        </CardHeader>
        <CardContent>
          <QueueTable entries={queue} />
          {queue.length === 0 && (
            <p className="text-muted-foreground text-sub py-4 text-center">隊列為空</p>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
