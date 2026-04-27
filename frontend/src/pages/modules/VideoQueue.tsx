import { useCallback, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoToQueue,
  advanceVideoQueue,
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
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FadeIn,
  Icon,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
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

const POLL_INTERVAL = 5_000

const MIN_VIEW_COUNT_OPTIONS = [
  { value: 0, label: '不限制' },
  { value: 500, label: '500+' },
  { value: 1_000, label: '1,000+' },
  { value: 5_000, label: '5,000+' },
  { value: 10_000, label: '10,000+' },
] as const

// redemption (channel points): starts at 1 video, up to 3 videos
const REDEMPTION_DURATION_OPTIONS = [
  { value: 300, label: '5 分鐘' },
  { value: 600, label: '10 分鐘' },
  { value: 900, label: '15 分鐘' },
] as const

/** Snap a raw seconds value to the nearest option in the list. */
function snapToOption(options: readonly { value: number }[], value: number): number {
  return options.reduce((prev, curr) =>
    Math.abs(curr.value - value) < Math.abs(prev.value - value) ? curr : prev
  ).value
}

// Source badge — label and Tailwind colour classes per source type
const SOURCE_CONFIG: Record<string, { label: string; className: string }> = {
  chat: { label: '聊天', className: 'text-muted-foreground' },
  redemption: {
    label: '兌換',
    className: 'border-violet-300 text-violet-600 dark:border-violet-700 dark:text-violet-400',
  },
  donation: {
    label: '斗內',
    className: 'border-amber-300 text-amber-600 dark:border-amber-700 dark:text-amber-400',
  },
  dashboard: {
    label: '主播',
    className: 'border-blue-300 text-blue-600 dark:border-blue-700 dark:text-blue-400',
  },
}

function ClipBadge() {
  return (
    <Badge
      variant="outline"
      className="shrink-0 text-[10px] px-1 py-0 text-purple-500 border-purple-400"
    >
      Clip
    </Badge>
  )
}

function SourceBadge({ source }: { source: string }) {
  const cfg = SOURCE_CONFIG[source] ?? { label: source, className: '' }
  return (
    <Badge variant="outline" className={`shrink-0 text-xs ${cfg.className}`}>
      {cfg.label}
    </Badge>
  )
}

function formatDuration(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function clampValue(value: string, min: number, max: number): string {
  const n = parseInt(value, 10)
  if (isNaN(n)) return String(min)
  return String(Math.min(max, Math.max(min, n)))
}

// Combined table: playing entry (highlighted) + queued entries with source column
function QueueTable({
  current,
  entries,
  onSkip,
  onSetNext,
  onPlayNow,
}: {
  current?: VideoQueueEntry | null
  entries: VideoQueueEntry[]
  onSkip?: () => void
  onSetNext?: (id: number) => void
  onPlayNow?: (id: number) => void
}) {
  const hasActions = !!(onSetNext || onPlayNow)
  if (!current && entries.length === 0) return null

  return (
    <div className="overflow-x-auto">
      {/* table-fixed: column widths are enforced by <th> — dynamic content can't shift fixed cols */}
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-10" />
            <TableHead>影片</TableHead>
            {/* 點播者 before 來源: logical "what + who" grouping, both can truncate independently */}
            <TableHead className="w-20 sm:w-28">點播者</TableHead>
            <TableHead className="hidden sm:table-cell w-20 text-center">來源</TableHead>
            <TableHead className="w-16 tabular-nums">長度</TableHead>
            {(hasActions || onSkip) && <TableHead className="w-20" />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* Currently playing row */}
          {current && (
            <TableRow className="bg-primary/5">
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
                    <Button variant="ghost" size="sm" onClick={onSkip} title="跳過當前影片">
                      <Icon icon="fa-solid fa-forward-step" className="size-3.5" />
                    </Button>
                  )}
                </TableCell>
              )}
            </TableRow>
          )}

          {/* Queued entries */}
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
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onSetNext(entry.id)}
                        title="排定為下一首"
                      >
                        <Icon icon="fa-solid fa-arrow-up-to-line" className="size-3.5" />
                      </Button>
                    )}
                    {onPlayNow && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => onPlayNow(entry.id)}
                        title="直接插播"
                      >
                        <Icon icon="fa-solid fa-play" className="size-3.5" />
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

  const { user, isAffiliate } = useAuth()
  const [state, setState] = useState<PublicVideoQueueState | null>(null)
  const [settings, setSettings] = useState<VideoQueueSettings | null>(null)
  const [loading, setLoading] = useState(true)

  const [helpOpen, setHelpOpen] = useState(false)
  const [maxRedemptionDurationValue, setMaxRedemptionDurationValue] = useState('600')
  const [maxQueueSizeInput, setMaxQueueSizeInput] = useState('')
  const [userCooldownInput, setUserCooldownInput] = useState('')
  const [maxPerUserInput, setMaxPerUserInput] = useState('')
  const [minViewCountValue, setMinViewCountValue] = useState('0')
  const [saving, setSaving] = useState(false)
  const [addUrlInput, setAddUrlInput] = useState('')
  const [adding, setAdding] = useState(false)
  const hasInitialized = useRef(false)

  const fetchData = useCallback(async () => {
    if (!isAffiliate) {
      setLoading(false)
      return
    }
    try {
      const [queueState, queueSettings] = await Promise.all([
        getVideoQueueState(),
        getVideoQueueSettings(),
      ])
      setState(queueState)
      setSettings(queueSettings)
      if (!hasInitialized.current) {
        setMaxRedemptionDurationValue(
          String(snapToOption(REDEMPTION_DURATION_OPTIONS, queueSettings.max_duration_redemption))
        )
        setMaxQueueSizeInput(String(queueSettings.max_queue_size))
        setUserCooldownInput(String(queueSettings.user_cooldown_seconds))
        setMaxPerUserInput(String(queueSettings.max_per_user))
        setMinViewCountValue(String(queueSettings.min_view_count))
        hasInitialized.current = true
      }
    } catch {
      // silent on poll errors
    } finally {
      setLoading(false)
    }
  }, [isAffiliate])

  usePolling({ fetchFn: fetchData, intervalMs: POLL_INTERVAL })

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ enabled })
      setSettings(updated)
      toast.success(enabled ? '影片佇列已啟用' : '影片佇列已停用')
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

  const handleSaveSettings = async () => {
    const redemptionDuration = parseInt(maxRedemptionDurationValue, 10)
    const queueSize = parseInt(maxQueueSizeInput, 10)
    const cooldown = parseInt(userCooldownInput, 10)
    const perUser = parseInt(maxPerUserInput, 10)
    const minViews = parseInt(minViewCountValue, 10)
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
        max_duration_redemption: redemptionDuration,
        max_queue_size: queueSize,
        user_cooldown_seconds: cooldown,
        max_per_user: perUser,
        min_view_count: minViews,
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
      let newState = await addVideoToQueue(addUrlInput.trim())
      // Nothing playing yet → advance immediately, mirroring the overlay's kickstart logic.
      // Uses the public advance endpoint intentionally: the overlay is the authoritative player
      // and the same unauthenticated endpoint is used there. No auth-gated advance exists.
      if (newState.current === null && newState.queue.length > 0 && user?.name) {
        newState = await advanceVideoQueue(user.name, null)
      }
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
      <PageMain>
        <PageHeader title="Video Queue" description="管理 YouTube 點播系統" />
        <div className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch">
          <div className="lg:col-span-8">
            <Card className="h-full">
              <CardHeader>
                <Skeleton className="h-5 w-24" />
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-2">
                  <Skeleton className="h-9 w-full" />
                  {Array.from({ length: 6 }).map((_, i) => (
                    <Skeleton key={i} className="h-12 w-full" />
                  ))}
                </div>
              </CardContent>
            </Card>
          </div>
          <div className="lg:col-span-4 flex flex-col gap-section">
            <Skeleton className="aspect-16/10 w-full rounded-xl" />
            <Skeleton className="h-24 w-full rounded-xl" />
            <Skeleton className="h-48 w-full rounded-xl" />
          </div>
        </div>
      </PageMain>
    )
  }

  const current = state?.current ?? null
  const queue = state?.queue ?? []
  const queueSize = state?.queue_size ?? 0
  const totalQueuedDuration = state?.total_queued_duration ?? null

  return (
    <PageMain className="relative">
      <div className="flex items-start justify-between gap-2">
        <PageHeader title="Video Queue" description="管理 YouTube 影片佇列" />
        <Button
          variant="ghost"
          size="icon"
          className="mt-0.5 shrink-0 border border-primary/40 text-muted-foreground hover:border-primary hover:text-primary/80"
          onClick={() => setHelpOpen(true)}
          title="使用說明"
        >
          <Icon
            icon="fa-regular fa-circle-question"
            wrapperClassName="size-5"
            className="text-[18px]"
          />
        </Button>
      </div>

      <Sheet open={helpOpen} onOpenChange={setHelpOpen}>
        <SheetContent side="right" className="w-80 sm:w-96">
          <SheetHeader>
            <SheetTitle>Video Queue 使用說明</SheetTitle>
            <SheetDescription>如何在 Twitch 設定點播獎勵並使用 Video Queue</SheetDescription>
          </SheetHeader>
          <div className="flex flex-col px-page py-2">
            {/* Step 1 — Twitch 新增獎勵 */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-brands fa-twitch"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
                <div className="mt-1 w-px flex-1 bg-border" />
              </div>
              <div className="flex flex-col gap-element pb-6">
                <p className="text-content font-semibold">Twitch 新增獎勵</p>
                <p className="text-sub text-muted-foreground">
                  建立自訂獎勵，供觀眾以點數兌換點播。
                </p>
                <ul className="flex flex-col gap-1">
                  {[
                    '後台 → 社群 → 忠誠點數 → 管理獎勵',
                    '新增自訂獎勵，設定名稱與點數花費',
                    '確認獎勵已啟用',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Step 2 — Events 綁定兌換 */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-solid fa-bolt"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
                <div className="mt-1 w-px flex-1 bg-border" />
              </div>
              <div className="flex flex-col gap-element pb-6">
                <p className="text-content font-semibold">Events 綁定兌換</p>
                <p className="text-sub text-muted-foreground">將 Twitch 獎勵與播放清單功能連結。</p>
                <ul className="flex flex-col gap-1">
                  {[
                    'Events → 忠誠點數兌換',
                    '「播放清單」列 → 選取剛建立的獎勵',
                    '確認狀態開關已開啟',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            {/* Step 3 — OBS Overlay */}
            <div className="flex gap-3">
              <div className="flex flex-col items-center">
                <div className="flex size-7 shrink-0 items-center justify-center rounded-full bg-primary/10 ring-1 ring-primary/20">
                  <Icon
                    icon="fa-solid fa-display"
                    wrapperClassName="size-3.5"
                    className="text-label text-primary"
                  />
                </div>
              </div>
              <div className="flex flex-col gap-element pb-2">
                <p className="text-content font-semibold">OBS 加入 Overlay</p>
                <p className="text-sub text-muted-foreground">
                  觀眾兌換後影片自動播放，佇列空時全透明。
                </p>
                <ul className="flex flex-col gap-1">
                  {[
                    '「佇列設定」右上角複製 Overlay URL',
                    'OBS 新增瀏覽器來源，貼上 URL（1920×1080）',
                    '來源屬性勾選「控制音訊（透過 OBS）」',
                    '混音器開啟「監聽並輸出」（預設靜音）',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-[5px] size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* Inline overlay for non-affiliates — blurs preview, blocks interaction */}
      {!isAffiliate && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-4 bg-background/80 backdrop-blur-sm">
          <Icon
            icon="fa-solid fa-lock"
            className="text-5xl text-muted-foreground"
            wrapperClassName="size-16"
          />
          <span className="text-sm text-muted-foreground">
            成為 Twitch 聯盟夥伴或合作夥伴後即可使用影片佇列功能
          </span>
        </div>
      )}

      {/* Row 1: Queue (col-8) always matches right column height */}
      <FadeIn inView className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch">
        {/* Queue card — fills full column height */}
        <div className="lg:col-span-8">
          <Card className="h-full">
            <CardHeader>
              <CardTitle>
                等待佇列
                <Badge variant="outline" className="ml-2">
                  {queueSize}
                  {totalQueuedDuration ? ` — ${formatDuration(totalQueuedDuration)}` : ''}
                </Badge>
              </CardTitle>
              <CardAction>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleClear}
                  disabled={!current && queueSize === 0}
                >
                  <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
                  清空
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-section pt-0">
              <div className="flex items-center gap-element">
                <div className="relative flex-1 sm:max-w-72">
                  <Icon
                    icon="fa-brands fa-youtube"
                    className="text-sm text-muted-foreground"
                    wrapperClassName="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
                  />
                  <Input
                    aria-label="YouTube 連結"
                    placeholder="貼上影片連結"
                    value={addUrlInput}
                    onChange={e => setAddUrlInput(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAddVideo()}
                    className="pl-8"
                  />
                </div>
                <Button size="sm" onClick={handleAddVideo} disabled={adding || !addUrlInput.trim()}>
                  <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
                  {adding ? (
                    <>
                      <Spinner className="mr-1.5" />
                      新增中
                    </>
                  ) : (
                    '新增'
                  )}
                </Button>
              </div>
              <QueueTable
                current={current}
                entries={queue}
                onSkip={handleSkip}
                onSetNext={handleSetNext}
                onPlayNow={handlePlayNow}
              />
              {!current && queue.length === 0 && (
                <div className="flex flex-1 flex-col items-center justify-center gap-section text-muted-foreground">
                  <Icon
                    icon="fa-solid fa-circle-play"
                    wrapperClassName="size-20 opacity-25"
                    className="text-[5rem]"
                  />
                  <div className="flex flex-col items-center gap-1">
                    <span className="text-sub font-medium">佇列為空</span>
                    <span className="text-label">貼上連結後按 Enter 或點擊「新增」</span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right sidebar: Preview + Now Playing + source toggles + overlay buttons */}
        <div className="flex flex-col gap-section lg:col-span-4">
          {/* Overlay preview iframe */}
          {overlayUrl && (
            <div className="aspect-[16/10] overflow-hidden rounded-lg border bg-black">
              <iframe
                src={`${overlayUrl}?preview=1`}
                className="block h-full w-full"
                title="Overlay 預覽"
                allow="autoplay"
              />
            </div>
          )}

          {/* Now Playing + controls */}
          <Card className="flex-1">
            <CardHeader>
              {/* Title is always fixed — only description content changes */}
              <CardTitle className="flex items-center gap-2">
                正在播放
                {/* Duration badge always rendered; invisible preserves height when absent */}
                <Badge
                  variant="secondary"
                  className={`text-xs tabular-nums ${current?.duration_seconds ? '' : 'invisible'}`}
                >
                  {current?.duration_seconds ? formatDuration(current.duration_seconds) : '--:--'}
                </Badge>
              </CardTitle>
              <CardDescription className="min-w-0">
                {/* Line 1: video title when playing, status text when idle */}
                <span className="block truncate" title={current?.title || current?.video_id}>
                  {current ? current.title || current.video_id : '目前沒有播放'}
                </span>
                {/* Line 2: always same DOM structure — invisible holds badge height */}
                <span className="flex items-center gap-1.5">
                  <span className={`min-w-0 truncate ${current ? '' : 'invisible'}`}>
                    {current?.requested_by ?? '\u00A0'}
                  </span>
                  <span className={`shrink-0 ${current ? '' : 'invisible'}`}>
                    <SourceBadge source={current?.source ?? 'dashboard'} />
                  </span>
                </span>
              </CardDescription>
              <CardAction>
                <Button size="sm" variant="outline" onClick={handleSkip} disabled={!current}>
                  <Icon icon="fa-solid fa-forward-step" className="mr-1.5 size-3" />
                  跳過
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="pb-5">
              <p className="text-label text-muted-foreground">
                {queueSize > 0
                  ? `待播 ${queueSize} 首${totalQueuedDuration ? ` · ${formatDuration(totalQueuedDuration)}` : ''}`
                  : '待播佇列為空'}
              </p>
            </CardContent>
          </Card>
        </div>
      </FadeIn>

      {/* Row 2: Queue settings */}
      <FadeIn inView delay={0.1}>
        <Card>
          <CardHeader>
            <CardTitle>佇列設定</CardTitle>
            <CardDescription>設定各來源的投稿限制條件</CardDescription>
            <CardAction>
              <div className="flex items-center gap-2 sm:gap-section">
                <div className="min-w-0 flex-1">
                  <OverlayUrlBlock url={overlayUrl} />
                </div>
                <Separator orientation="vertical" className="h-6" />
                <div className="flex shrink-0 items-center gap-element">
                  <Switch
                    id="vq-enabled"
                    checked={settings?.enabled ?? false}
                    onCheckedChange={handleToggleEnabled}
                  />
                  <Label htmlFor="vq-enabled" className="cursor-pointer text-sub font-normal">
                    啟用
                  </Label>
                </div>
              </div>
            </CardAction>
          </CardHeader>

          <CardContent className="flex flex-col gap-section">
            {/* Global limits — apply to all sources */}
            <div className="flex flex-col gap-3">
              <p className="text-sub text-muted-foreground">全域限制</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-3 gap-y-3 sm:gap-x-8 lg:grid-cols-4">
                <div className="flex items-center gap-3">
                  <Label htmlFor="max-per-user" className="w-24 shrink-0">
                    每人排隊上限
                  </Label>
                  <Input
                    id="max-per-user"
                    type="number"
                    min={0}
                    max={20}
                    placeholder="0"
                    value={maxPerUserInput}
                    onChange={e => setMaxPerUserInput(e.target.value)}
                    onBlur={e => setMaxPerUserInput(clampValue(e.target.value, 0, 20))}
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
                    onBlur={e => setUserCooldownInput(clampValue(e.target.value, 0, 3600))}
                    className="w-20"
                  />
                  <span className="text-muted-foreground text-sub">秒</span>
                </div>

                <div className="flex items-center gap-3">
                  <Label htmlFor="min-view-count" className="w-24 shrink-0">
                    最低觀看數
                  </Label>
                  <Select value={minViewCountValue} onValueChange={setMinViewCountValue}>
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

                <div className="flex items-center gap-3">
                  <Label htmlFor="max-queue-size" className="w-24 shrink-0">
                    佇列上限
                  </Label>
                  <Input
                    id="max-queue-size"
                    type="number"
                    min={1}
                    max={100}
                    placeholder="20"
                    value={maxQueueSizeInput}
                    onChange={e => setMaxQueueSizeInput(e.target.value)}
                    onBlur={e => setMaxQueueSizeInput(clampValue(e.target.value, 1, 100))}
                    className="w-20"
                  />
                  <span className="text-muted-foreground text-sub">首</span>
                </div>
              </div>
            </div>

            <Separator />

            {/* Redemption-specific settings */}
            <div className="flex flex-col gap-3">
              <p className="text-sub text-muted-foreground">忠誠點數兌換</p>
              <div className="flex items-center gap-element">
                <Switch
                  id="redemption-enabled"
                  checked={settings?.redemption_enabled ?? false}
                  onCheckedChange={handleToggleRedemptionEnabled}
                />
                <Label htmlFor="redemption-enabled" className="cursor-pointer">
                  啟用點數兌換
                </Label>
              </div>
              <div className="flex items-center gap-3">
                <Label htmlFor="max-redemption-duration" className="w-24 shrink-0">
                  影片長度上限
                </Label>
                <Select
                  value={maxRedemptionDurationValue}
                  onValueChange={setMaxRedemptionDurationValue}
                >
                  <SelectTrigger id="max-redemption-duration" className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REDEMPTION_DURATION_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={String(opt.value)}>
                        {opt.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex justify-end">
              <Button size="sm" onClick={handleSaveSettings} disabled={saving}>
                {saving && <Spinner className="mr-1.5" />}
                儲存
              </Button>
            </div>
          </CardContent>
        </Card>
      </FadeIn>
    </PageMain>
  )
}
