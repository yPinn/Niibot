import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  type CommunityOverlayAccess,
  type CommunityOverlayTheme,
  type CommunityOverlayThemeState,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  getCommunityOverlaySettings,
  getCommunityOverlayThemeSettings,
  publishCommunityOverlayTheme,
  resetCommunityOverlayThemeDraft,
  rotateCommunityOverlayKey,
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
  Skeleton,
  Switch,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import { CheckinTriggerCard } from './communityOverlay/CheckinTriggerCard'
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
  useDocumentTitle('Community Overlay')

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
        getCommunityOverlayThemeSettings(),
      ])
      setAccess(nextAccess)
      setThemeState(nextTheme)
      setDraftTheme(nextTheme.draft)
    } catch (error) {
      setLoadFailed(true)
      toastApiError(error, 'Community Overlay 載入失敗')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (preview) return

    let active = true

    void Promise.all([getCommunityOverlaySettings(), getCommunityOverlayThemeSettings()])
      .then(([settings, theme]) => {
        if (!active) return
        setAccess(settings)
        setThemeState(theme)
        setDraftTheme(theme.draft)
      })
      .catch(error => {
        if (!active) return
        setLoadFailed(true)
        toastApiError(error, 'Community Overlay 載入失敗')
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

  const handleEnabledChange = async (enabled: boolean) => {
    if (!access || mutationLocked.current) return
    mutationLocked.current = true
    setMutation('enabled')
    try {
      const next = preview
        ? { ...access, enabled, updated_at: new Date().toISOString() }
        : await updateCommunityOverlaySettings(enabled)
      setAccess(next)
      toast.success(`共用 Overlay 已${next.enabled ? '啟用' : '停用'}`)
    } catch (error) {
      toastApiError(error, '更新共用 Overlay 失敗')
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
      toast.success('Overlay 連結已輪替，請更新 OBS Browser Source')
    } catch (error) {
      toastApiError(error, '輪替 Overlay 連結失敗')
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
      applyThemeState(await getCommunityOverlayThemeSettings())
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
          await updateCommunityOverlayThemeDraft(draftTheme, themeState.draft_version)
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
        applyThemeState(await publishCommunityOverlayTheme(themeState.draft_version))
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
        applyThemeState(await resetCommunityOverlayThemeDraft(themeState.draft_version))
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

  return (
    <PageMain>
      <PageHeader
        title="Community Overlay"
        description="管理簽到方式、OBS 連線、樣式發布與社群事件預覽"
      />

      {loading ? (
        <SettingsSkeleton />
      ) : loadFailed || !access || !themeState ? (
        <Alert variant="destructive">
          <Icon icon="fa-solid fa-circle-exclamation" />
          <AlertTitle>Community Overlay 載入失敗</AlertTitle>
          <AlertDescription>
            <p>目前無法取得這個頻道的 Overlay 設定。</p>
            <Button size="sm" variant="outline" onClick={() => void loadSettings()}>
              重新載入
            </Button>
          </AlertDescription>
        </Alert>
      ) : (
        <div className="flex flex-col gap-8">
          <section
            aria-labelledby="community-overlay-checkin-title"
            className="flex flex-col gap-3"
          >
            <SettingsSectionHeader
              id="community-overlay-checkin-title"
              title="簽到方式"
              description="保留聊天指令簽到，並可另外綁定由 Twitch 管理的頻道點數獎勵。"
            />
            <SlideUp>
              <CheckinTriggerCard
                config={checkinConfig}
                rewards={twitchRewards}
                loading={checkinLoading}
                loadFailed={checkinLoadFailed}
                isAffiliate={isAffiliate}
                onRetry={() => void loadCheckinTrigger()}
              />
            </SlideUp>
          </section>

          <section
            aria-labelledby="community-overlay-connection-title"
            className="flex flex-col gap-3"
          >
            <SettingsSectionHeader
              id="community-overlay-connection-title"
              title="OBS 連線"
              description="設定 Browser Source、控制事件顯示，並管理這個頻道專屬的存取連結。"
            />
            <SlideUp>
              <Card className="min-w-0">
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2">
                    OBS Browser Source
                    <Badge variant={access.enabled ? 'default' : 'outline'}>
                      {access.enabled ? '已啟用' : '已停用'}
                    </Badge>
                  </CardTitle>
                  <CardDescription>
                    將網址加入 OBS；簽到與後續社群事件會共用同一個透明畫面來源。
                  </CardDescription>
                  <CardAction className="flex items-center gap-2">
                    <span className="hidden text-label text-muted-foreground sm:inline">
                      顯示事件
                    </span>
                    <Switch
                      aria-label="啟用共用 Overlay"
                      checked={access.enabled}
                      disabled={mutation !== null}
                      onCheckedChange={value => void handleEnabledChange(value)}
                    />
                  </CardAction>
                </CardHeader>
                <CardContent className="grid min-w-0 gap-section xl:grid-cols-[minmax(0,1.35fr)_minmax(18rem,0.65fr)] xl:items-start">
                  <div className="flex min-w-0 flex-col gap-2">
                    <p className="text-content font-semibold">頻道專屬網址</p>
                    <p className="text-sub text-muted-foreground">
                      建議設為 1920 × 1080，背景保持透明。網址內含頻道存取 key，請勿公開分享。
                    </p>
                    <OverlayUrlBlock url={overlayUrl} />
                  </div>

                  <div className="flex min-w-0 flex-col gap-2 rounded-lg bg-muted p-section sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <p className="text-content font-semibold">需要撤銷舊連結？</p>
                      <p className="text-label text-muted-foreground">
                        輪替後，舊 Browser Source 會立即停止取得事件。
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
                          輪替 Overlay 連結
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>輪替 Overlay 連結？</AlertDialogTitle>
                          <AlertDialogDescription>
                            舊網址會立即失效。完成後必須把新網址貼回 OBS Browser Source。
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>取消</AlertDialogCancel>
                          <AlertDialogAction onClick={() => void handleRotateKey()}>
                            確認輪替
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                </CardContent>
              </Card>
            </SlideUp>
          </section>

          <section
            aria-labelledby="community-overlay-appearance-title"
            className="flex flex-col gap-3"
          >
            <SettingsSectionHeader
              id="community-overlay-appearance-title"
              title="樣式與發布"
              description="調整此頻道的集點卡草稿，確認預覽後再發布到 OBS。"
            />
            <SlideUp>
              <Card>
                <CardContent>
                  <ThemeEditor
                    theme={draftTheme}
                    localDirty={!themesEqual(draftTheme, themeState.draft)}
                    hasUnpublishedChanges={themeState.has_unpublished_changes}
                    busy={themeMutation}
                    onChange={setDraftTheme}
                    onSave={() => void handleSaveTheme()}
                    onPublish={() => void handlePublishTheme()}
                    onReset={() => void handleResetTheme()}
                  />
                </CardContent>
              </Card>
            </SlideUp>
          </section>

          <section
            aria-labelledby="community-overlay-testing-title"
            className="flex flex-col gap-3"
          >
            <SettingsSectionHeader
              id="community-overlay-testing-title"
              title="預覽與測試"
              description="確認已發布效果；開發環境可從 Twitch 送出不影響正式紀錄的測試事件。"
            />
            <SlideUp className="grid grid-cols-1 gap-section lg:grid-cols-12">
              <Card className={import.meta.env.DEV ? 'lg:col-span-7' : 'lg:col-span-12'}>
                <CardHeader>
                  <CardTitle>已發布事件預覽</CardTitle>
                  <CardDescription>預覽會重播尚未過期的開發測試事件。</CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <div className="relative aspect-video overflow-hidden rounded-lg border bg-muted/40">
                    <div
                      aria-hidden="true"
                      className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground"
                    >
                      <Icon icon="fa-solid fa-clapperboard" wrapperClassName="size-6" />
                      <span className="text-label">等待 Overlay 事件</span>
                    </div>
                    {previewUrl && (
                      <iframe
                        src={previewUrl}
                        title="共用 Overlay 預覽"
                        referrerPolicy="no-referrer"
                        className="absolute inset-0 block h-full w-full"
                      />
                    )}
                  </div>
                  <p className="text-label text-muted-foreground">
                    正式 OBS 網址不帶 preview 參數，因此重新連線時不會重播舊事件。
                  </p>
                </CardContent>
              </Card>

              {import.meta.env.DEV && (
                <Card className="lg:col-span-5">
                  <CardHeader>
                    <CardTitle>開發測試</CardTitle>
                    <CardDescription>
                      確認 Twitch 指令、事件 feed 與 OBS 動畫整段串接。
                    </CardDescription>
                  </CardHeader>
                  <CardContent className="grid gap-section md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                    <ol className="flex flex-col gap-2 text-sub text-muted-foreground">
                      <li>1. 保持上方預覽開啟，並確認共用 Overlay 為啟用狀態。</li>
                      <li>
                        2. 由頻道主播在 Twitch 聊天室輸入{' '}
                        <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                          !ovltest 8
                        </code>
                        。
                      </li>
                      <li>3. 預覽應顯示第 8 天集點卡動畫；事件約 10 分鐘後失效。</li>
                    </ol>
                    <div className="rounded-lg border border-dashed px-section py-3 text-label text-muted-foreground md:max-w-72">
                      <Icon icon="fa-solid fa-flask" className="mr-2 text-primary" />
                      測試事件只送到 Overlay，不會寫入正式簽到紀錄或增加天數。
                    </div>
                  </CardContent>
                </Card>
              )}
            </SlideUp>
          </section>
        </div>
      )}
    </PageMain>
  )
}
