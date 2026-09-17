import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  addVideoToQueue,
  advanceVideoQueue,
  type BlocklistKind,
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
import { Icon, SlideUp } from '@/components/primitives'
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  Skeleton,
  Switch,
} from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useVideoQueueStream } from '@/hooks/useVideoQueueStream'
import { toastApiError } from '@/lib/toast-error'

import { BlocklistSection, type BlocklistSectionHandle } from './BlocklistSection'
import { NowPlayingCard } from './NowPlayingCard'
import { OverlayCard } from './OverlayCard'
import { type HistoryState, QueueCard, type QueueTab } from './QueueCard'
import { RulesCard, type RulesDraft } from './RulesCard'
import { SetupGuideSheet } from './SetupGuideSheet'
import { QUEUE_PAGE_SIZE, REDEMPTION_DURATION_OPTIONS, snapToOption, watchUrl } from './utils'

const EMPTY_DRAFT: RulesDraft = {
  maxDurationMinutes: '',
  minViewCount: '0',
  replayCooldownHours: '',
  maxPerUser: '',
  userCooldownSeconds: '',
  maxQueueSize: '',
  maxRedemptionDuration: '600',
}

export default function VideoQueue() {
  useDocumentTitle('Video Queue')

  const { user, isAffiliate } = useAuth()
  // Queue state rides the same NOTIFY-woken SSE stream as the OBS overlay;
  // settings are fetched once (they only change from this page).
  const {
    state,
    setState,
    status: streamStatus,
  } = useVideoQueueStream(isAffiliate ? user?.name : undefined)
  const [settings, setSettings] = useState<VideoQueueSettings | null>(null)
  const [loading, setLoading] = useState(true)

  const [helpOpen, setHelpOpen] = useState(false)
  const [draft, setDraft] = useState<RulesDraft>(EMPTY_DRAFT)
  const [saving, setSaving] = useState(false)
  const [addUrlInput, setAddUrlInput] = useState('')
  const [adding, setAdding] = useState(false)
  const hasInitialized = useRef(false)

  const [tab, setTab] = useState<QueueTab>('queue')
  const [history, setHistory] = useState<VideoQueueHistoryEntry[]>([])
  const [historyCursor, setHistoryCursor] = useState<string | null>(null)
  const [historyState, setHistoryState] = useState<HistoryState>('idle')
  const [historyPage, setHistoryPage] = useState(0)

  const blocklistRef = useRef<BlocklistSectionHandle>(null)

  const setField = useCallback((key: keyof RulesDraft, value: string) => {
    setDraft(d => ({ ...d, [key]: value }))
  }, [])

  const loadHistory = useCallback(async (cursor?: string): Promise<boolean> => {
    setHistoryState(cursor ? 'more' : 'loading')
    try {
      const page = await getVideoQueueHistory(cursor)
      setHistory(prev => (cursor ? [...prev, ...page.entries] : page.entries))
      setHistoryCursor(page.next_cursor)
      return page.entries.length > 0
    } catch (e) {
      toastApiError(e, '載入播放紀錄失敗')
      return false
    } finally {
      setHistoryState('ready')
    }
  }, [])

  const handleTabChange = (next: QueueTab) => {
    setTab(next)
    if (next === 'history' && historyState === 'idle') void loadHistory()
  }

  // History is fetched forward-only (cursor). Pages already loaded are just
  // sliced client-side; hitting "next" past the loaded window fetches first.
  const historyCanNext =
    (historyPage + 1) * QUEUE_PAGE_SIZE < history.length || historyCursor !== null
  const handleHistoryNext = async () => {
    if ((historyPage + 1) * QUEUE_PAGE_SIZE < history.length) {
      setHistoryPage(p => p + 1)
      return
    }
    if (historyCursor && (await loadHistory(historyCursor))) {
      setHistoryPage(p => p + 1)
    }
  }

  const handleRequeue = async (entry: VideoQueueHistoryEntry) => {
    try {
      await addVideoToQueue(watchUrl(entry.video_type, entry.video_id))
      toast.success('已重新加入佇列')
    } catch (e) {
      toastApiError(e, '重新點播失敗')
    }
  }

  const handleBlockFromHistory = async (entry: VideoQueueHistoryEntry, kind: BlocklistKind) => {
    let value: string | null
    let label: string | null
    if (kind === 'creator') {
      value = entry.creator_id
      label = entry.creator_name ?? entry.creator_id
    } else if (kind === 'user') {
      value = entry.requested_by_id ?? entry.requested_by
      label = entry.requested_by
    } else {
      value = entry.video_id
      label = entry.title ?? entry.video_id
    }
    if (!value) return
    try {
      await blocklistRef.current?.addBlock(kind, value, label)
      toast.success('已加入封鎖清單')
    } catch (e) {
      toastApiError(e, '加入封鎖清單失敗')
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
        setDraft({
          maxDurationMinutes: String(Math.round(queueSettings.max_duration_seconds / 60)),
          minViewCount: String(queueSettings.min_view_count),
          replayCooldownHours: String(queueSettings.replay_cooldown_hours),
          maxPerUser: String(queueSettings.max_per_user),
          userCooldownSeconds: String(queueSettings.user_cooldown_seconds),
          maxQueueSize: String(queueSettings.max_queue_size),
          maxRedemptionDuration: String(
            snapToOption(REDEMPTION_DURATION_OPTIONS, queueSettings.max_duration_redemption)
          ),
        })
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
    const redemptionDuration = parseInt(draft.maxRedemptionDuration, 10)
    const queueSize = parseInt(draft.maxQueueSize, 10)
    const cooldown = parseInt(draft.userCooldownSeconds, 10)
    const perUser = parseInt(draft.maxPerUser, 10)
    const minViews = parseInt(draft.minViewCount, 10)
    const maxDurationMinutes = parseInt(draft.maxDurationMinutes, 10)
    const replayCooldownHours = parseInt(draft.replayCooldownHours, 10)
    if (isNaN(queueSize) || queueSize < 1 || queueSize > 100) {
      toast.error('佇列最多：1 ~ 100 首')
      return
    }
    if (isNaN(cooldown) || cooldown < 0 || cooldown > 3600) {
      toast.error('兩次點播間隔：0 ~ 3600 秒')
      return
    }
    if (isNaN(perUser) || perUser < 0 || perUser > 20) {
      toast.error('每人同時最多：0 ~ 20 首（0 為不限）')
      return
    }
    if (isNaN(maxDurationMinutes) || maxDurationMinutes < 0 || maxDurationMinutes > 1440) {
      toast.error('影片最長：0 ~ 1440 分（0 為不限）')
      return
    }
    if (isNaN(replayCooldownHours) || replayCooldownHours < 0 || replayCooldownHours > 168) {
      toast.error('播過多久內不能再點：0 ~ 168 小時（0 為不限）')
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
        max_duration_seconds: maxDurationMinutes * 60,
        replay_cooldown_hours: replayCooldownHours,
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
      setState(await skipCurrentVideo())
      toast.success('已跳過當前影片')
    } catch (e) {
      toastApiError(e, '跳過失敗')
    }
  }

  const handleClear = async () => {
    try {
      setState(await clearVideoQueue())
      toast.success('已清空佇列')
    } catch (e) {
      toastApiError(e, '清空失敗')
    }
  }

  const handleSetNext = async (entryId: number) => {
    try {
      setState(await setVideoAsNext(entryId))
      toast.success('已排到最前面')
    } catch (e) {
      toastApiError(e, '排序失敗')
    }
  }

  const handlePlayNow = async (entryId: number) => {
    try {
      setState(await playVideoNow(entryId))
      toast.success('已插播')
    } catch (e) {
      toastApiError(e, '插播失敗')
    }
  }

  const handleRemove = async (entryId: number) => {
    try {
      setState(await removeQueueEntry(entryId))
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
      toast.success('已加入佇列')
    } catch (e) {
      toastApiError(e, '新增失敗')
    } finally {
      setAdding(false)
    }
  }

  const overlayUrl = user?.name ? `${window.location.origin}/${user.name}/video-queue/overlay` : ''

  const current = state?.current ?? null
  const queue = state?.queue ?? []
  const queueSize = state?.queue_size ?? 0
  const totalQueuedDuration = state?.total_queued_duration ?? null

  const headerActions = (
    <div className="flex items-center gap-2">
      {isAffiliate && (
        <div className="flex items-center gap-1.5">
          <Switch
            id="vq-enabled"
            checked={settings?.enabled ?? false}
            onCheckedChange={handleToggleEnabled}
          />
          <Label htmlFor="vq-enabled" className="cursor-pointer text-sub font-normal">
            啟用
          </Label>
        </div>
      )}
      <Button variant="ghost" size="icon" onClick={() => setHelpOpen(true)} title="使用說明">
        <Icon icon="fa-regular fa-circle-question" wrapperClassName="size-5" />
        <span className="sr-only">使用說明</span>
      </Button>
    </div>
  )

  if (loading) {
    return (
      <PageMain>
        <PageHeader title="Video Queue" description="管理觀眾點播的影片">
          {headerActions}
        </PageHeader>
        <Skeleton className="h-52 w-full rounded-xl" />
        <div className="grid grid-cols-1 gap-section lg:grid-cols-12">
          <Skeleton className="h-96 w-full rounded-xl lg:col-span-8" />
          <Skeleton className="h-96 w-full rounded-xl lg:col-span-4" />
        </div>
      </PageMain>
    )
  }

  return (
    <PageMain>
      <PageHeader title="Video Queue" description="管理觀眾點播的影片">
        {headerActions}
      </PageHeader>

      <SetupGuideSheet open={helpOpen} onOpenChange={setHelpOpen} />

      {!isAffiliate && <AffiliateLockOverlay message="取得資格後可使用影片佇列功能" fullPage />}

      {streamStatus === 'reconnecting' && (
        <WarningBanner>即時更新暫時中斷，重新連線中…畫面可能不是最新狀態</WarningBanner>
      )}

      <SlideUp inView>
        <NowPlayingCard
          current={current}
          next={queue[0]}
          queueSize={queueSize}
          totalQueuedDuration={totalQueuedDuration}
          onSkip={handleSkip}
        />
      </SlideUp>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-stretch"
      >
        <div className="lg:col-span-8">
          <QueueCard
            tab={tab}
            onTabChange={handleTabChange}
            queue={queue}
            queueSize={queueSize}
            totalQueuedDuration={totalQueuedDuration}
            addUrlInput={addUrlInput}
            onAddUrlChange={setAddUrlInput}
            adding={adding}
            onAdd={handleAddVideo}
            onClear={handleClear}
            canClear={!!current || queueSize > 0}
            onSetNext={handleSetNext}
            onPlayNow={handlePlayNow}
            onRemove={handleRemove}
            history={history}
            historyState={historyState}
            historyPage={historyPage}
            historyCanPrev={historyPage > 0}
            historyCanNext={historyCanNext}
            onHistoryPrev={() => setHistoryPage(p => Math.max(0, p - 1))}
            onHistoryNext={() => void handleHistoryNext()}
            onRequeue={handleRequeue}
            onBlock={handleBlockFromHistory}
          />
        </div>
        <div className="lg:col-span-4">
          <OverlayCard url={overlayUrl} current={current} onOpenGuide={() => setHelpOpen(true)} />
        </div>
      </SlideUp>

      <SlideUp
        inView
        delay={0.1}
        className="grid grid-cols-1 gap-section lg:grid-cols-12 lg:items-start"
      >
        <div className="lg:col-span-8">
          <RulesCard
            draft={draft}
            onField={setField}
            redemptionEnabled={settings?.redemption_enabled ?? false}
            onToggleRedemption={handleToggleRedemptionEnabled}
            onSave={handleSaveSettings}
            saving={saving}
          />
        </div>
        <div className="lg:col-span-4">
          <Card>
            <CardHeader>
              <CardTitle>封鎖清單</CardTitle>
              <CardDescription>
                符合的影片、標題關鍵字或點播者，所有點播管道都會拒絕
              </CardDescription>
            </CardHeader>
            <CardContent>
              <BlocklistSection ref={blocklistRef} hideHeader />
            </CardContent>
          </Card>
        </div>
      </SlideUp>
    </PageMain>
  )
}
