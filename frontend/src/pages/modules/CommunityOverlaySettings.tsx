import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  type CommunityOverlayAccess,
  type CommunityOverlayContentType,
  type CommunityOverlayTheme,
  type CommunityOverlayThemeState,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  getCommunityOverlaySettings,
  getCommunityOverlayThemeSettings,
  publishCommunityOverlayTheme,
  resetCommunityOverlayThemeDraft,
  rotateCommunityOverlayKey,
  triggerCommunityOverlayPreview,
  updateCommunityOverlaySettings,
  updateCommunityOverlayThemeDraft,
} from '@/api/communityOverlay'
import { ApiError } from '@/api/errors'
import {
  getRedemptionConfigs,
  getTwitchRewards,
  NonPartnerError,
  type RedemptionConfig,
  type TwitchReward,
} from '@/api/events'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { Icon, SlideUp, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  AlertTitle,
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
  Skeleton,
  Switch,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import { CheckinBlockCard } from './communityOverlay/CheckinBlockCard'
import { ThemeEditor } from './communityOverlay/ThemeEditor'

function SettingsSkeleton() {
  return (
    <div className="flex flex-col gap-8">
      <Skeleton className="h-72 rounded-xl" />
      <Skeleton className="h-[36rem] rounded-xl" />
      <Skeleton className="h-72 rounded-xl" />
    </div>
  )
}

const DEV_PREVIEW_ACCESS: CommunityOverlayAccess = {
  public_key: '11111111-1111-4111-8111-111111111111',
  enabled: true,
  created_at: '2026-08-31T00:00:00Z',
  updated_at: '2026-08-31T00:00:00Z',
}

const DEV_PREVIEW_THEME_STATE: CommunityOverlayThemeState = {
  block_type: 'checkin',
  renderer: 'checkin-card',
  schema_version: 1,
  draft_version: 1,
  draft: DEFAULT_COMMUNITY_OVERLAY_THEME,
  published: {
    revision_id: 1,
    renderer: 'checkin-card',
    schema_version: 1,
    theme: DEFAULT_COMMUNITY_OVERLAY_THEME,
    created_at: '2026-08-31T00:00:00Z',
  },
  has_unpublished_changes: false,
  updated_at: '2026-08-31T00:00:00Z',
}

const DEV_PREVIEW_CHECKIN_CONFIG: RedemptionConfig = {
  id: 1,
  channel_id: 'preview-channel',
  action_type: 'checkin',
  reward_name: '每日簽到',
  reward_id: 'preview-checkin-reward',
  enabled: true,
}

const DEV_PREVIEW_CHECKIN_REWARD: TwitchReward = {
  id: 'preview-checkin-reward',
  title: '每日簽到',
  cost: 10,
  is_enabled: true,
  is_paused: false,
  is_in_stock: true,
  should_redemptions_skip_request_queue: true,
  max_per_stream: 100,
  max_per_user_per_stream: 1,
}

function themesEqual(left: CommunityOverlayTheme, right: CommunityOverlayTheme): boolean {
  return (
    left.surface_color === right.surface_color &&
    left.accent_color === right.accent_color &&
    left.text_color === right.text_color &&
    left.placement === right.placement &&
    left.radius_px === right.radius_px &&
    left.display_ms === right.display_ms &&
    left.motion === right.motion
  )
}

interface CommunityOverlaySettingsProps {
  preview?: boolean
}

function SettingsSectionHeader({
  id,
  title,
  description,
}: {
  id: string
  title: string
  description: string
}) {
  return (
    <div className="max-w-3xl">
      <h2 id={id} className="text-section-title font-semibold">
        {title}
      </h2>
      <p className="mt-1 text-sub text-muted-foreground">{description}</p>
    </div>
  )
}

export default function CommunityOverlaySettings({
  preview = false,
}: CommunityOverlaySettingsProps) {
  useDocumentTitle('Live Display')

  const [access, setAccess] = useState<CommunityOverlayAccess | null>(
    preview ? DEV_PREVIEW_ACCESS : null
  )
  const [themeState, setThemeState] = useState<CommunityOverlayThemeState | null>(
    preview ? DEV_PREVIEW_THEME_STATE : null
  )
  const [draftTheme, setDraftTheme] = useState<CommunityOverlayTheme>(DEV_PREVIEW_THEME_STATE.draft)
  const [loading, setLoading] = useState(!preview)
  const [loadFailed, setLoadFailed] = useState(false)
  const [mutation, setMutation] = useState<'enabled' | 'key' | null>(null)
  const mutationLocked = useRef(false)
  const [themeMutation, setThemeMutation] = useState<'save' | 'publish' | 'reset' | null>(null)
  const themeMutationLocked = useRef(false)
  const [previewMutation, setPreviewMutation] = useState(false)
  const previewMutationLocked = useRef(false)
  const [expandedBlock, setExpandedBlock] = useState<CommunityOverlayContentType | null>('checkin')
  const [previewMode, setPreviewMode] = useState<'draft' | 'live'>('draft')
  const [connectionOpen, setConnectionOpen] = useState(false)
  const [checkinConfig, setCheckinConfig] = useState<RedemptionConfig | null>(
    preview ? DEV_PREVIEW_CHECKIN_CONFIG : null
  )
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>(
    preview ? [DEV_PREVIEW_CHECKIN_REWARD] : []
  )
  const [checkinLoading, setCheckinLoading] = useState(!preview)
  const [checkinLoadFailed, setCheckinLoadFailed] = useState(false)
  const [isAffiliate, setIsAffiliate] = useState(true)

  const loadSettings = async () => {
    setLoading(true)
    setLoadFailed(false)
    try {
      const [nextAccess, nextTheme] = await Promise.all([
        getCommunityOverlaySettings(),
        getCommunityOverlayThemeSettings('checkin'),
      ])
      setAccess(nextAccess)
      setThemeState(nextTheme)
      setDraftTheme(nextTheme.draft)
    } catch (error) {
      setLoadFailed(true)
      toastApiError(error, 'Live Display 載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (preview) return

    let active = true

    void Promise.all([getCommunityOverlaySettings(), getCommunityOverlayThemeSettings('checkin')])
      .then(([settings, theme]) => {
        if (!active) return
        setAccess(settings)
        setThemeState(theme)
        setDraftTheme(theme.draft)
      })
      .catch(error => {
        if (!active) return
        setLoadFailed(true)
        toastApiError(error, 'Live Display 載入失敗')
      })
      .finally(() => {
        if (active) setLoading(false)
      })

    return () => {
      active = false
    }
  }, [preview])

  const loadCheckinTrigger = async () => {
    if (preview) return
    setCheckinLoading(true)
    setCheckinLoadFailed(false)
    setIsAffiliate(true)

    const [configsResult, rewardsResult] = await Promise.allSettled([
      getRedemptionConfigs(),
      getTwitchRewards(),
    ])

    if (configsResult.status === 'fulfilled') {
      setCheckinConfig(configsResult.value.find(config => config.action_type === 'checkin') ?? null)
    } else {
      setCheckinLoadFailed(true)
    }

    if (rewardsResult.status === 'fulfilled') {
      setTwitchRewards([...rewardsResult.value].sort((left, right) => left.cost - right.cost))
    } else if (rewardsResult.reason instanceof NonPartnerError) {
      setIsAffiliate(false)
      setTwitchRewards([])
    } else {
      setCheckinLoadFailed(true)
    }

    setCheckinLoading(false)
  }

  useEffect(() => {
    if (preview) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadCheckinTrigger()
    // This loader is intentionally independent from the Overlay access/theme request.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview])

  const overlayUrl = useMemo(
    () =>
      access
        ? `${window.location.origin}/community-overlay#key=${encodeURIComponent(access.public_key)}`
        : undefined,
    [access]
  )
  const previewUrl = overlayUrl ? `${overlayUrl}&preview=1` : undefined
  const localThemeDirty = themeState ? !themesEqual(draftTheme, themeState.draft) : false
  const themeStatus = localThemeDirty
    ? '尚未儲存'
    : themeState?.has_unpublished_changes
      ? '草稿未發布'
      : '已發布'

  const handleEnabledChange = async (enabled: boolean) => {
    if (!access || mutationLocked.current) return
    mutationLocked.current = true
    setMutation('enabled')
    try {
      const next = preview
        ? { ...access, enabled, updated_at: new Date().toISOString() }
        : await updateCommunityOverlaySettings(enabled)
      setAccess(next)
      toast.success(`直播畫面顯示已${next.enabled ? '啟用' : '停用'}`)
    } catch (error) {
      toastApiError(error, '更新直播畫面顯示失敗')
    } finally {
      mutationLocked.current = false
      setMutation(null)
    }
  }

  const handleRotateKey = async () => {
    if (mutationLocked.current) return
    mutationLocked.current = true
    setMutation('key')
    try {
      const next = preview
        ? {
            ...DEV_PREVIEW_ACCESS,
            enabled: access?.enabled ?? true,
            public_key: '22222222-2222-4222-8222-222222222222',
            updated_at: new Date().toISOString(),
          }
        : await rotateCommunityOverlayKey()
      setAccess(next)
      toast.success('OBS 顯示連結已更新，請貼回 Browser Source')
    } catch (error) {
      toastApiError(error, '更新 OBS 顯示連結失敗')
    } finally {
      mutationLocked.current = false
      setMutation(null)
    }
  }

  const applyThemeState = (next: CommunityOverlayThemeState) => {
    setThemeState(next)
    setDraftTheme(next.draft)
  }

  const refreshThemeAfterConflict = async (error: unknown) => {
    if (!(error instanceof ApiError) || error.code !== 'COMMUNITY_OVERLAY.THEME_CONFLICT') return
    try {
      applyThemeState(await getCommunityOverlayThemeSettings('checkin'))
    } catch {
      // Keep the local draft visible if the conflict refresh also fails.
    }
  }

  const handleSaveTheme = async () => {
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation('save')
    try {
      if (preview) {
        applyThemeState({
          ...themeState,
          draft: draftTheme,
          draft_version: themeState.draft_version + 1,
          has_unpublished_changes: true,
        })
      } else {
        applyThemeState(
          await updateCommunityOverlayThemeDraft('checkin', draftTheme, themeState.draft_version)
        )
      }
      toast.success('Overlay 樣式草稿已儲存')
    } catch (error) {
      toastApiError(error, '儲存 Overlay 樣式草稿失敗')
      await refreshThemeAfterConflict(error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const handlePublishTheme = async () => {
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation('publish')
    try {
      if (preview) {
        applyThemeState({
          ...themeState,
          published: { ...themeState.published, theme: themeState.draft },
          has_unpublished_changes: false,
        })
      } else {
        applyThemeState(await publishCommunityOverlayTheme('checkin', themeState.draft_version))
      }
      toast.success('Overlay 樣式已發布至 OBS')
    } catch (error) {
      toastApiError(error, '發布 Overlay 樣式失敗')
      await refreshThemeAfterConflict(error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const handleResetTheme = async () => {
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation('reset')
    try {
      if (preview) {
        const next = {
          ...themeState,
          draft: themeState.published.theme,
          draft_version: themeState.draft_version + 1,
          has_unpublished_changes: false,
        }
        applyThemeState(next)
      } else {
        applyThemeState(await resetCommunityOverlayThemeDraft('checkin', themeState.draft_version))
      }
      toast.success('草稿已還原為目前發布版本')
    } catch (error) {
      toastApiError(error, '還原 Overlay 樣式草稿失敗')
      await refreshThemeAfterConflict(error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const handlePreview = async () => {
    if (previewMutationLocked.current) return
    previewMutationLocked.current = true
    setPreviewMode('live')
    setPreviewMutation(true)
    try {
      if (!preview) await triggerCommunityOverlayPreview('checkin')
      toast.success('測試動畫已送出')
    } catch (error) {
      toastApiError(error, '測試動畫送出失敗')
      setPreviewMode('draft')
    } finally {
      previewMutationLocked.current = false
      setPreviewMutation(false)
    }
  }

  return (
    <PageMain className="w-full min-w-0">
      <PageHeader title="Live Display" description="管理會顯示在直播畫面上的互動卡片。" />

      {loading ? (
        <SettingsSkeleton />
      ) : loadFailed || !access || !themeState ? (
        <Alert variant="destructive">
          <Icon icon="fa-solid fa-circle-exclamation" />
          <AlertTitle>Live Display 載入失敗</AlertTitle>
          <AlertDescription>
            <p>目前無法取得這個頻道的顯示設定。</p>
            <Button size="sm" variant="outline" onClick={() => void loadSettings()}>
              重新載入
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <div className="flex min-w-0 flex-col gap-8">
          <section
            aria-labelledby="live-display-content-title"
            className="flex min-w-0 flex-col gap-3"
          >
            <SettingsSectionHeader
              id="live-display-content-title"
              title="顯示內容"
              description="選擇要出現在直播畫面的內容；每項都能直接測試，不會增加正式紀錄。"
            />
            <SlideUp>
              <CheckinBlockCard
                config={checkinConfig}
                rewards={twitchRewards}
                loading={checkinLoading}
                loadFailed={checkinLoadFailed}
                isAffiliate={isAffiliate}
                testing={previewMutation}
                open={expandedBlock === 'checkin'}
                themeStatus={themeStatus}
                themeChanged={localThemeDirty || themeState.has_unpublished_changes}
                onOpenChange={open => setExpandedBlock(open ? 'checkin' : null)}
                onRetry={() => void loadCheckinTrigger()}
                onTest={() => void handlePreview()}
              >
                <ThemeEditor
                  theme={draftTheme}
                  localDirty={localThemeDirty}
                  hasUnpublishedChanges={themeState.has_unpublished_changes}
                  busy={themeMutation}
                  previewUrl={previewUrl}
                  previewMode={previewMode}
                  onChange={setDraftTheme}
                  onPreviewModeChange={setPreviewMode}
                  onSave={() => void handleSaveTheme()}
                  onPublish={() => void handlePublishTheme()}
                  onReset={() => void handleResetTheme()}
                />
              </CheckinBlockCard>
            </SlideUp>
          </section>

          <section
            aria-labelledby="live-display-connection-title"
            className="flex min-w-0 flex-col gap-3"
          >
            <SettingsSectionHeader
              id="live-display-connection-title"
              title="加入直播畫面"
              description="初次使用時，將頻道專屬連結加入 OBS Browser Source。"
            />
            <SlideUp>
              <Collapsible open={connectionOpen} onOpenChange={setConnectionOpen}>
                <Card className="min-w-0">
                  <CardHeader className="has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[1fr_auto]">
                    <CardTitle className="flex flex-wrap items-center gap-2">
                      OBS 連線
                      <Badge variant={access.enabled ? 'default' : 'outline'}>
                        {access.enabled ? '已啟用' : '已停用'}
                      </Badge>
                    </CardTitle>
                    <CardDescription>
                      所有互動卡片共用這個透明畫面來源；通常只需設定一次。
                    </CardDescription>
                    <CardAction className="col-start-1 row-span-1 row-start-3 flex flex-wrap items-center justify-start gap-2 justify-self-stretch sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:justify-end sm:justify-self-end">
                      <Switch
                        aria-label="啟用直播畫面顯示"
                        checked={access.enabled}
                        disabled={mutation !== null}
                        onCheckedChange={value => void handleEnabledChange(value)}
                      />
                      <CollapsibleTrigger asChild>
                        <Button
                          size="sm"
                          variant="ghost"
                          aria-label={connectionOpen ? '收合 OBS 連線設定' : '顯示 OBS 連線設定'}
                        >
                          <Icon
                            icon="fa-solid fa-chevron-down"
                            className={`text-label transition-transform ${connectionOpen ? 'rotate-180' : ''}`}
                          />
                          {connectionOpen ? '收合設定' : '連線設定'}
                        </Button>
                      </CollapsibleTrigger>
                    </CardAction>
                  </CardHeader>
                  <CollapsibleContent>
                    <CardContent className="grid min-w-0 gap-section border-t pt-card xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] xl:items-start">
                      <div className="flex min-w-0 flex-col gap-2">
                        <p className="text-content font-semibold">頻道專屬網址</p>
                        <p className="text-sub text-muted-foreground">
                          建議設為 1920 × 1080 並保持透明背景。此連結只供 OBS 使用，請勿公開分享。
                        </p>
                        <OverlayUrlBlock
                          url={overlayUrl}
                          copyLabel="點擊以複製 OBS 顯示連結"
                          openLabel="開啟 OBS 顯示畫面"
                        />
                      </div>

                      <div className="flex min-w-0 flex-col gap-2 rounded-lg bg-muted p-section sm:flex-row sm:items-center sm:justify-between">
                        <div className="min-w-0">
                          <p className="text-content font-semibold">需要撤銷舊連結？</p>
                          <p className="text-label text-muted-foreground">
                            更新後，OBS 內的舊連結會立即停止顯示內容。
                          </p>
                        </div>
                        <AlertDialog>
                          <AlertDialogTrigger asChild>
                            <Button
                              variant="outline"
                              className="shrink-0 self-start sm:self-auto"
                              disabled={mutation !== null}
                            >
                              {mutation === 'key' ? (
                                <Spinner className="mr-1.5" />
                              ) : (
                                <Icon icon="fa-solid fa-key" className="mr-1.5 text-label" />
                              )}
                              更新 OBS 顯示連結
                            </Button>
                          </AlertDialogTrigger>
                          <AlertDialogContent>
                            <AlertDialogHeader>
                              <AlertDialogTitle>更新 OBS 顯示連結？</AlertDialogTitle>
                              <AlertDialogDescription>
                                舊連結會立即失效。完成後請把新連結貼回 OBS Browser Source。
                              </AlertDialogDescription>
                            </AlertDialogHeader>
                            <AlertDialogFooter>
                              <AlertDialogCancel>取消</AlertDialogCancel>
                              <AlertDialogAction onClick={() => void handleRotateKey()}>
                                確認更新
                              </AlertDialogAction>
                            </AlertDialogFooter>
                          </AlertDialogContent>
                        </AlertDialog>
                      </div>
                    </CardContent>
                  </CollapsibleContent>
                </Card>
              </Collapsible>
            </SlideUp>
          </section>
        </div>
      )}
    </PageMain>
  )
}
