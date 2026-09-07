import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoToQueue,
  advanceVideoQueue,
  clearVideoQueue,
  getVideoQueueHistory,
  getVideoQueueSettings,
  playVideoNow,
  removeQueueEntry,
  setVideoAsNext,
  skipCurrentVideo,
  updateVideoQueueSettings,
  type VideoQueueHistoryEntry,
  type VideoQueueSettings,
} from '@/api/videoQueue'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { EmptyState, Icon, SlideUp, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Progress,
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
  SheetSection,
  SheetTitle,
  Skeleton,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useVideoQueueStream } from '@/hooks/useVideoQueueStream'
import { toastApiError } from '@/lib/toast-error'

import { HistoryTable } from './videoQueue/HistoryTable'
import { QueueTable, SourceBadge } from './videoQueue/QueueTable'
import {
  clampValue,
  formatDuration,
  MIN_VIEW_COUNT_OPTIONS,
  REDEMPTION_DURATION_OPTIONS,
  snapToOption,
  thumbnailUrl,
  watchUrl,
} from './videoQueue/utils'

export default function VideoQueue() {
  useDocumentTitle('Video Queue')

  const { user, isAffiliate } = useAuth()
  // Queue state rides the same NOTIFY-woken SSE stream as the OBS overlay;
  // settings are fetched once (they only change from this page).
  const { state, setState } = useVideoQueueStream(isAffiliate ? user?.name : undefined)
  const [settings, setSettings] = useState<VideoQueueSettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [now, setNow] = useState(() => Date.now())

  const [helpOpen, setHelpOpen] = useState(false)
  // The preview loads the real overlay in an iframe. It stays a click-to-load
  // poster by default: the overlay can't autoplay muted for every platform
  // (Twitch clips especially), and the "正在播放" card already shows live status.
  const [previewOpen, setPreviewOpen] = useState(false)
  const [maxRedemptionDurationValue, setMaxRedemptionDurationValue] = useState('600')
  const [maxQueueSizeInput, setMaxQueueSizeInput] = useState('')
  const [userCooldownInput, setUserCooldownInput] = useState('')
  const [maxPerUserInput, setMaxPerUserInput] = useState('')
  const [minViewCountValue, setMinViewCountValue] = useState('0')
  const [saving, setSaving] = useState(false)
  const [addUrlInput, setAddUrlInput] = useState('')
  const [adding, setAdding] = useState(false)
  const hasInitialized = useRef(false)

  const [tab, setTab] = useState<'queue' | 'history'>('queue')
  const [history, setHistory] = useState<VideoQueueHistoryEntry[]>([])
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'more' | 'ready'>('idle')

  const loadHistory = useCallback(async (cursor?: string) => {
    setHistoryState(cursor ? 'more' : 'loading')
    try {
      const page = await getVideoQueueHistory(cursor)
      setHistory(prev => (cursor ? [...prev, ...page.entries] : page.entries))
      setHistoryCursor(page.next_cursor)
    } catch (e) {
      toastApiError(e, '載入播放紀錄失敗')
    } finally {
      setHistoryState('ready')
    }
  }, [])

  const handleShowHistory = () => {
    setTab('history')
    if (historyState === 'idle') void loadHistory()
  }

  const handleRequeue = async (entry: VideoQueueHistoryEntry) => {
    try {
      await addVideoToQueue(watchUrl(entry.video_type, entry.video_id))
      toast.success('已重新加入佇列')
    } catch (e) {
      toastApiError(e, '重新點播失敗')
    }
  }

  const fetchSettings = useCallback(async () => {
    if (!isAffiliate) {
      setLoading(false)
      return
    }
    try {
      const queueSettings = await getVideoQueueSettings()
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
      // silent — settings keep their last-known value
    } finally {
      setLoading(false)
    }
  }, [isAffiliate])

  // Settings: one fetch on mount, plus a refresh when the tab regains focus
  // (the stream keeps queue state live on its own).
  useEffect(() => {
    const timeoutId = window.setTimeout(() => void fetchSettings(), 0)
    const onVisible = () => {
      if (document.visibilityState === 'visible') void fetchSettings()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      window.clearTimeout(timeoutId)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [fetchSettings])

  // Advance a 1s wall-clock ticker only while something is playing; the elapsed
  // value itself is derived from it at render time.
  const currentStartedAt = state?.current?.started_at
  useEffect(() => {
    if (!currentStartedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [currentStartedAt])

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ enabled })
      setSettings(updated)
      toast.success(enabled ? '影片佇列已啟用' : '影片佇列已停用')
    } catch (e) {
      toastApiError(e, '更新失敗')
    }
  }

  const handleToggleRedemptionEnabled = async (redemption_enabled: boolean) => {
    try {
      const updated = await updateVideoQueueSettings({ redemption_enabled })
      setSettings(updated)
      toast.success(redemption_enabled ? '點數兌換已開啟' : '點數兌換已關閉')
    } catch (e) {
      toastApiError(e, '更新失敗')
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
    } catch (e) {
      toastApiError(e, '更新失敗')
    } finally {
      setSaving(false)
    }
  }

  const handleSkip = async () => {
    try {
      const newState = await skipCurrentVideo()
      setState(newState)
      toast.success('已跳過當前影片')
    } catch (e) {
      toastApiError(e, '跳過失敗')
    }
  }

  const handleClear = async () => {
    try {
      const newState = await clearVideoQueue()
      setState(newState)
      toast.success('已清空隊列')
    } catch (e) {
      toastApiError(e, '清空失敗')
    }
  }

  const handleSetNext = async (entryId: number) => {
    try {
      const newState = await setVideoAsNext(entryId)
      setState(newState)
      toast.success('已移至下一首')
    } catch (e) {
      toastApiError(e, '排序失敗')
    }
  }

  const handlePlayNow = async (entryId: number) => {
    try {
      const newState = await playVideoNow(entryId)
      setState(newState)
      toast.success('已插播')
    } catch (e) {
      toastApiError(e, '插播失敗')
    }
  }

  const handleRemove = async (entryId: number) => {
    try {
      const newState = await removeQueueEntry(entryId)
      setState(newState)
      toast.success('已移除')
    } catch (e) {
      toastApiError(e, '移除失敗')
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
      toastApiError(e, '新增失敗')
    } finally {
      setAdding(false)
    }
  }

  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/video-queue/overlay` : ''

  if (loading) {
    return (
      <PageMain>
        <PageHeader title="Video Queue" description="管理影片播放佇列" />
        <div className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch">
          <div className="lg:col-span-8">
            <Card className="h-full">
              <CardHeader>
                <Skeleton className="h-5 w-24" />
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-element">
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
  const currentThumb = current ? thumbnailUrl(current.video_type, current.video_id) : null
  const elapsed = current?.started_at
    ? Math.max(0, (now - new Date(current.started_at).getTime()) / 1000)
    : 0
  const playbackProgress =
    current?.duration_seconds && current.duration_seconds > 0
      ? Math.min(100, (elapsed / current.duration_seconds) * 100)
      : 0

  return (
    <PageMain>
      <div className="flex items-start justify-between gap-2">
        <PageHeader title="Video Queue" description="管理影片播放佇列" />
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
            className="text-card-title"
          />
        </Button>
      </div>

      <Sheet open={helpOpen} onOpenChange={setHelpOpen}>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>Video Queue 使用說明</SheetTitle>
            <SheetDescription>如何在 Twitch 設定點播獎勵並使用 Video Queue</SheetDescription>
          </SheetHeader>
          <SheetSection className="flex flex-col flex-1 overflow-y-auto">
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
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
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
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
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
                    'OBS 新增瀏覽器來源，貼上 URL（建議 640×400）',
                    '來源屬性勾選「使用 OBS 控制音訊」',
                    '混音器開啟「監聽並輸出」（預設靜音）',
                  ].map(item => (
                    <li key={item} className="flex items-start gap-1.5">
                      <span className="mt-1.25 size-1 shrink-0 rounded-full bg-muted-foreground/50" />
                      <span className="text-label text-muted-foreground">{item}</span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </SheetSection>
        </SheetContent>
      </Sheet>

      {!isAffiliate && <AffiliateLockOverlay message="取得資格後可使用影片佇列功能" fullPage />}

      <SlideUp inView className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch">
        <div className="lg:col-span-8">
          <Card className="h-full">
            <CardHeader>
              <Tabs
                value={tab}
                onValueChange={v => (v === 'history' ? handleShowHistory() : setTab('queue'))}
              >
                <TabsList>
                  <TabsTrigger value="queue">
                    佇列
                    <Badge variant="outline" className="ml-1.5">
                      {queueSize}
                      {totalQueuedDuration ? ` · ${formatDuration(totalQueuedDuration)}` : ''}
                    </Badge>
                  </TabsTrigger>
                  <TabsTrigger value="history">紀錄</TabsTrigger>
                </TabsList>
              </Tabs>
              {tab === 'queue' && (
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
              )}
            </CardHeader>
            <CardContent className="flex flex-1 flex-col gap-section pt-0">
              {tab === 'queue' ? (
                <>
                  <div className="flex items-center gap-element">
                    <div className="relative flex-1 sm:max-w-72">
                      <Icon
                        icon="fa-solid fa-link"
                        className="text-sub text-muted-foreground"
                        wrapperClassName="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2"
                      />
                      <Input
                        aria-label="影片連結"
                        placeholder="貼上影片連結（YouTube／Twitch Clip／Bilibili）"
                        value={addUrlInput}
                        onChange={e => setAddUrlInput(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && handleAddVideo()}
                        className="pl-8"
                      />
                    </div>
                    <Button
                      size="sm"
                      onClick={handleAddVideo}
                      disabled={adding || !addUrlInput.trim()}
                    >
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
                    onRemove={handleRemove}
                  />
                  {!current && queue.length === 0 && (
                    <EmptyState
                      icon="fa-solid fa-circle-play"
                      title="佇列為空"
                      description="貼上連結後按 Enter 或點擊「新增」"
                    />
                  )}
                </>
              ) : historyState === 'loading' ? (
                <div className="flex flex-col gap-element">
                  {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : (
                <HistoryTable
                  entries={history}
                  hasMore={historyCursor !== null}
                  loadingMore={historyState === 'more'}
                  onLoadMore={() => historyCursor && void loadHistory(historyCursor)}
                  onRequeue={handleRequeue}
                />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="flex flex-col gap-section lg:col-span-4">
          {overlayUrl && (
            <div className="relative aspect-16/10 overflow-hidden rounded-lg border bg-black">
              {previewOpen ? (
                <iframe
                  src={`${overlayUrl}?preview=1`}
                  className="block h-full w-full"
                  title="Overlay 預覽"
                  allow="autoplay"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => setPreviewOpen(true)}
                  className="group absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/80 hover:text-white"
                >
                  {currentThumb && (
                    <img
                      src={currentThumb}
                      alt=""
                      className="absolute inset-0 h-full w-full object-cover opacity-40 transition-opacity group-hover:opacity-55"
                    />
                  )}
                  <Icon
                    icon="fa-solid fa-circle-play"
                    wrapperClassName="relative size-9"
                    className="size-9"
                  />
                  <span className="relative text-sub">
                    {current ? '載入 Overlay 預覽（靜音）' : '載入 Overlay 預覽'}
                  </span>
                </button>
              )}
            </div>
          )}

          <Card className="flex-1">
            <CardHeader>
              {/* Title is always fixed — only description content changes */}
              <CardTitle className="flex items-center gap-2">
                正在播放
                {/* Time badge always rendered; invisible preserves height when absent */}
                <Badge
                  variant="secondary"
                  className={`text-label tabular-nums ${current ? '' : 'invisible'}`}
                >
                  {current
                    ? `${formatDuration(elapsed)} / ${current.duration_seconds ? formatDuration(current.duration_seconds) : '--:--'}`
                    : '--:--'}
                </Badge>
              </CardTitle>
              <CardDescription className="min-w-0">
                <span className="block truncate" title={current?.title || current?.video_id}>
                  {current ? current.title || current.video_id : '目前沒有播放'}
                </span>
                {/* Line 2: always same DOM structure — invisible holds badge height */}
                <span className="flex items-center gap-1.5">
                  <span className={`min-w-0 truncate ${current ? '' : 'invisible'}`}>
                    {current?.requested_by ?? ' '}
                  </span>
                  <span className={`shrink-0 ${current ? '' : 'invisible'}`}>
                    <SourceBadge source={current?.source ?? 'dashboard'} />
                  </span>
                </span>
              </CardDescription>
              <CardAction className="flex items-center gap-1">
                {current && (
                  <Button size="icon-sm" variant="ghost" asChild title="在新分頁開啟">
                    <a
                      href={watchUrl(current.video_type, current.video_id)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <Icon icon="fa-solid fa-arrow-up-right-from-square" className="size-3" />
                    </a>
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={handleSkip} disabled={!current}>
                  <Icon icon="fa-solid fa-forward-step" className="mr-1.5 size-3" />
                  跳過
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-col gap-element pb-5">
              {current && (
                <div className="flex gap-element">
                  {currentThumb && (
                    <img
                      src={currentThumb}
                      alt=""
                      className="aspect-video w-24 shrink-0 rounded-md border object-cover"
                    />
                  )}
                  <div className="flex min-w-0 flex-1 flex-col justify-center gap-1.5">
                    <Progress segments={[{ value: playbackProgress }]} aria-label="播放進度" />
                    <span className="text-label text-muted-foreground tabular-nums">
                      {current.duration_seconds
                        ? `剩餘 ${formatDuration(Math.max(0, current.duration_seconds - elapsed))}`
                        : '長度未知'}
                    </span>
                  </div>
                </div>
              )}
              <p className="text-label text-muted-foreground">
                {queueSize > 0
                  ? `待播 ${queueSize} 首${totalQueuedDuration ? ` · ${formatDuration(totalQueuedDuration)}` : ''}`
                  : '待播佇列為空'}
              </p>
            </CardContent>
          </Card>
        </div>
      </SlideUp>

      <SlideUp inView delay={0.1}>
        <Card>
          <CardHeader>
            <CardTitle>佇列設定</CardTitle>
            <CardDescription>設定各來源的投稿限制條件</CardDescription>
            <CardAction>
              <div className="flex items-center gap-2 sm:gap-section">
                <div className="hidden sm:block min-w-0 flex-1">
                  <OverlayUrlBlock url={overlayUrl} />
                </div>
                <Separator orientation="vertical" className="hidden sm:block h-6" />
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
            <div className="sm:hidden">
              <OverlayUrlBlock url={overlayUrl} />
            </div>
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
      </SlideUp>
    </PageMain>
  )
}
