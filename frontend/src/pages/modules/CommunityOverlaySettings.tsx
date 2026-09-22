import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  type CommunityOverlayAccess,
  type CommunityOverlayContentType,
  type CommunityOverlayTheme,
  type CommunityOverlayThemeState,
  DEFAULT_COMMUNITY_OVERLAY_THEME,
  DEFAULT_TAROT_OVERLAY_THEME,
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
import { getCollectionBinderChoreographyDurationMs } from '@/components/community-overlay/collectionBinderMotion'
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
  CARD_HEADER_STACK_ON_MOBILE,
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

import { CheckinBlockCard } from './communityOverlay/CheckinBlockCard'
import { TarotBlockCard } from './communityOverlay/TarotBlockCard'
import { ThemeEditor, ThemePreview } from './communityOverlay/ThemeEditor'

const CONTENT_TYPES: CommunityOverlayContentType[] = ['checkin', 'tarot']

function SettingsSkeleton() {
  return (
    <div
      data-layout="live-display-workspace"
      className="grid grid-cols-1 gap-section xl:min-h-0 xl:flex-1 xl:grid-cols-12 xl:grid-rows-[minmax(0,1fr)] xl:items-stretch xl:overflow-hidden"
    >
      <div
        data-layout-column="content"
        data-layout-scroll="content"
        className="flex min-w-0 flex-col gap-element xl:col-span-8 xl:h-full xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain"
      >
        <Skeleton data-layout-panel="checkin" className="h-[36rem] rounded-xl" />
        <Skeleton data-layout-panel="tarot" className="h-72 rounded-xl" />
      </div>
      <div
        data-layout-column="support"
        data-layout-position="fixed"
        className="flex min-w-0 flex-col gap-section xl:sticky xl:top-0 xl:col-span-4 xl:max-h-full xl:self-start xl:overflow-y-auto xl:overscroll-contain"
      >
        <Skeleton data-layout-panel="connection" className="h-72 rounded-xl" />
        <Skeleton data-layout-panel="preview" className="h-96 rounded-xl" />
      </div>
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

const DEV_PREVIEW_TAROT_THEME_STATE: CommunityOverlayThemeState = {
  ...DEV_PREVIEW_THEME_STATE,
  block_type: 'tarot',
  renderer: 'tarot-card',
  draft: DEFAULT_TAROT_OVERLAY_THEME,
  published: {
    ...DEV_PREVIEW_THEME_STATE.published,
    renderer: 'tarot-card',
    theme: DEFAULT_TAROT_OVERLAY_THEME,
  },
}

const DEV_PREVIEW_CHECKIN_CONFIG: RedemptionConfig = {
  id: 1,
  channel_id: 'preview-channel',
  action_type: 'checkin',
  reward_name: '每日簽到',
  reward_id: 'preview-checkin-reward',
  enabled: true,
  first_message: '$(@user) 恭喜你搶到沙發！',
  first_announce_color: 'primary',
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

export default function CommunityOverlaySettings({
  preview = false,
}: CommunityOverlaySettingsProps) {
  useDocumentTitle('Live Display')

  const [access, setAccess] = useState<CommunityOverlayAccess | null>(
    preview ? DEV_PREVIEW_ACCESS : null
  )
  const [themeStates, setThemeStates] = useState<
    Record<CommunityOverlayContentType, CommunityOverlayThemeState | null>
  >({
    checkin: preview ? DEV_PREVIEW_THEME_STATE : null,
    tarot: preview ? DEV_PREVIEW_TAROT_THEME_STATE : null,
  })
  const [draftThemes, setDraftThemes] = useState<
    Record<CommunityOverlayContentType, CommunityOverlayTheme>
  >({
    checkin: DEV_PREVIEW_THEME_STATE.draft,
    tarot: DEV_PREVIEW_TAROT_THEME_STATE.draft,
  })
  const [loading, setLoading] = useState(!preview)
  const [loadFailed, setLoadFailed] = useState(false)
  const [mutation, setMutation] = useState<'enabled' | 'key' | null>(null)
  const mutationLocked = useRef(false)
  const [themeMutation, setThemeMutation] = useState<{
    blockType: CommunityOverlayContentType
    action: 'save' | 'publish' | 'reset'
  } | null>(null)
  const themeMutationLocked = useRef(false)
  const [previewMutation, setPreviewMutation] = useState<CommunityOverlayContentType | null>(null)
  const previewMutationLocked = useRef(false)
  const previewAutoCloseTimers = useRef<Partial<Record<CommunityOverlayContentType, number>>>({})

  useEffect(() => {
    const timers = previewAutoCloseTimers.current
    return () => {
      for (const timerId of Object.values(timers)) {
        if (timerId !== undefined) window.clearTimeout(timerId)
      }
    }
  }, [])
  const [expandedBlock, setExpandedBlock] = useState<CommunityOverlayContentType | null>('checkin')
  const [selectedBlock, setSelectedBlock] = useState<CommunityOverlayContentType>('checkin')
  const [previewModes, setPreviewModes] = useState<
    Record<CommunityOverlayContentType, 'draft' | 'live'>
  >({ checkin: 'draft', tarot: 'draft' })
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
      const [nextAccess, checkinTheme, tarotTheme] = await Promise.all([
        getCommunityOverlaySettings(),
        getCommunityOverlayThemeSettings('checkin'),
        getCommunityOverlayThemeSettings('tarot'),
      ])
      setAccess(nextAccess)
      setThemeStates({ checkin: checkinTheme, tarot: tarotTheme })
      setDraftThemes({ checkin: checkinTheme.draft, tarot: tarotTheme.draft })
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

    void Promise.all([
      getCommunityOverlaySettings(),
      getCommunityOverlayThemeSettings('checkin'),
      getCommunityOverlayThemeSettings('tarot'),
    ])
      .then(([settings, checkinTheme, tarotTheme]) => {
        if (!active) return
        setAccess(settings)
        setThemeStates({ checkin: checkinTheme, tarot: tarotTheme })
        setDraftThemes({ checkin: checkinTheme.draft, tarot: tarotTheme.draft })
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
        ? `${window.location.origin}/live-display#key=${encodeURIComponent(access.public_key)}`
        : undefined,
    [access]
  )
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

  const applyThemeState = (
    blockType: CommunityOverlayContentType,
    next: CommunityOverlayThemeState
  ) => {
    setThemeStates(current => ({ ...current, [blockType]: next }))
    setDraftThemes(current => ({ ...current, [blockType]: next.draft }))
  }

  const refreshThemeAfterConflict = async (
    blockType: CommunityOverlayContentType,
    error: unknown
  ) => {
    if (!(error instanceof ApiError) || error.code !== 'COMMUNITY_OVERLAY.THEME_CONFLICT') return
    try {
      applyThemeState(blockType, await getCommunityOverlayThemeSettings(blockType))
    } catch {
      // Keep the local draft visible if the conflict refresh also fails.
    }
  }

  const handleSaveTheme = async (blockType: CommunityOverlayContentType) => {
    const themeState = themeStates[blockType]
    const draftTheme = draftThemes[blockType]
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation({ blockType, action: 'save' })
    try {
      if (preview) {
        applyThemeState(blockType, {
          ...themeState,
          draft: draftTheme,
          draft_version: themeState.draft_version + 1,
          has_unpublished_changes: true,
        })
      } else {
        applyThemeState(
          blockType,
          await updateCommunityOverlayThemeDraft(blockType, draftTheme, themeState.draft_version)
        )
      }
      toast.success('Overlay 樣式草稿已儲存')
    } catch (error) {
      toastApiError(error, '儲存 Overlay 樣式草稿失敗')
      await refreshThemeAfterConflict(blockType, error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const handlePublishTheme = async (blockType: CommunityOverlayContentType) => {
    const themeState = themeStates[blockType]
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation({ blockType, action: 'publish' })
    try {
      if (preview) {
        applyThemeState(blockType, {
          ...themeState,
          published: { ...themeState.published, theme: themeState.draft },
          has_unpublished_changes: false,
        })
      } else {
        applyThemeState(
          blockType,
          await publishCommunityOverlayTheme(blockType, themeState.draft_version)
        )
      }
      toast.success('Overlay 樣式已發布至 OBS')
    } catch (error) {
      toastApiError(error, '發布 Overlay 樣式失敗')
      await refreshThemeAfterConflict(blockType, error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const handleResetTheme = async (blockType: CommunityOverlayContentType) => {
    const themeState = themeStates[blockType]
    if (!themeState || themeMutationLocked.current) return
    themeMutationLocked.current = true
    setThemeMutation({ blockType, action: 'reset' })
    try {
      if (preview) {
        const next = {
          ...themeState,
          draft: themeState.published.theme,
          draft_version: themeState.draft_version + 1,
          has_unpublished_changes: false,
        }
        applyThemeState(blockType, next)
      } else {
        applyThemeState(
          blockType,
          await resetCommunityOverlayThemeDraft(blockType, themeState.draft_version)
        )
      }
      toast.success('草稿已還原為目前發布版本')
    } catch (error) {
      toastApiError(error, '還原 Overlay 樣式草稿失敗')
      await refreshThemeAfterConflict(blockType, error)
    } finally {
      themeMutationLocked.current = false
      setThemeMutation(null)
    }
  }

  const clearPreviewAutoClose = (blockType: CommunityOverlayContentType) => {
    const timerId = previewAutoCloseTimers.current[blockType]
    if (timerId !== undefined) {
      window.clearTimeout(timerId)
      previewAutoCloseTimers.current[blockType] = undefined
    }
  }

  const schedulePreviewAutoClose = (blockType: CommunityOverlayContentType) => {
    clearPreviewAutoClose(blockType)
    // The iframe shows the published revision. Collection previews also honor
    // the binder's five-second choreography floor before returning to the draft.
    const configuredDisplayMs = themeStates[blockType]?.published.theme.display_ms ?? 5_000
    const displayMs =
      blockType === 'checkin'
        ? getCollectionBinderChoreographyDurationMs(configuredDisplayMs)
        : configuredDisplayMs
    previewAutoCloseTimers.current[blockType] = window.setTimeout(() => {
      previewAutoCloseTimers.current[blockType] = undefined
      setPreviewModes(current => ({ ...current, [blockType]: 'draft' }))
    }, displayMs + 1_500)
  }

  const handlePreview = async (blockType: CommunityOverlayContentType) => {
    if (previewMutationLocked.current) return
    previewMutationLocked.current = true
    setPreviewModes(current => ({ ...current, [blockType]: 'live' }))
    setPreviewMutation(blockType)
    try {
      if (!preview) await triggerCommunityOverlayPreview(blockType)
      toast.success('測試動畫已送出')
      schedulePreviewAutoClose(blockType)
    } catch (error) {
      toastApiError(error, '測試動畫送出失敗')
      setPreviewModes(current => ({ ...current, [blockType]: 'draft' }))
    } finally {
      previewMutationLocked.current = false
      setPreviewMutation(null)
    }
  }

  const handleBlockOpenChange = (blockType: CommunityOverlayContentType, open: boolean) => {
    if (open) setSelectedBlock(blockType)
    setExpandedBlock(open ? blockType : null)
  }

  const handleBlockPreview = (blockType: CommunityOverlayContentType) => {
    setSelectedBlock(blockType)
    void handlePreview(blockType)
  }

  const getThemePresentation = (blockType: CommunityOverlayContentType) => {
    const themeState = themeStates[blockType]
    const localDirty = themeState ? !themesEqual(draftThemes[blockType], themeState.draft) : false
    const status = localDirty
      ? '尚未儲存'
      : themeState?.has_unpublished_changes
        ? '草稿未發布'
        : '已發布'
    return { themeState, localDirty, status }
  }

  const renderThemeEditor = (blockType: CommunityOverlayContentType) => {
    const { themeState, localDirty } = getThemePresentation(blockType)
    if (!themeState) return null
    return (
      <ThemeEditor
        contentType={blockType}
        theme={draftThemes[blockType]}
        localDirty={localDirty}
        hasUnpublishedChanges={themeState.has_unpublished_changes}
        busy={themeMutation?.blockType === blockType ? themeMutation.action : null}
        onChange={next => setDraftThemes(current => ({ ...current, [blockType]: next }))}
        onSave={() => void handleSaveTheme(blockType)}
        onPublish={() => void handlePublishTheme(blockType)}
        onReset={() => void handleResetTheme(blockType)}
      />
    )
  }

  const renderThemePreview = (blockType: CommunityOverlayContentType) => {
    const developmentSample = preview ? `&sample=${blockType}` : ''
    const scopedPreviewUrl = overlayUrl
      ? `${overlayUrl}&preview=1&block=${blockType}${developmentSample}`
      : undefined
    return (
      <ThemePreview
        contentType={blockType}
        theme={draftThemes[blockType]}
        livePlacement={themeStates[blockType]?.published.theme.placement}
        previewUrl={scopedPreviewUrl}
        previewMode={previewModes[blockType]}
        onPreviewModeChange={mode => {
          clearPreviewAutoClose(blockType)
          setPreviewModes(current => ({ ...current, [blockType]: mode }))
        }}
      />
    )
  }

  return (
    <PageMain className="h-full w-full min-w-0 xl:overflow-y-hidden">
      <PageHeader
        title="Live Display"
        description="設定直播內容與 OBS 連線。"
        className="shrink-0"
      />

      {loading ? (
        <SettingsSkeleton />
      ) : loadFailed || !access || CONTENT_TYPES.some(type => !themeStates[type]) ? (
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
        <div
          data-layout="live-display-workspace"
          className="grid grid-cols-1 gap-section xl:min-h-0 xl:flex-1 xl:grid-cols-12 xl:grid-rows-[minmax(0,1fr)] xl:items-stretch xl:overflow-hidden"
        >
          <section
            aria-labelledby="live-display-content-title"
            data-layout-column="content"
            data-layout-scroll="content"
            className="flex min-w-0 flex-col gap-element xl:col-span-8 xl:h-full xl:min-h-0 xl:overflow-y-auto xl:overscroll-contain"
          >
            <h2 id="live-display-content-title" className="sr-only">
              顯示內容
            </h2>
            <SlideUp data-layout-start="cards">
              <div className="flex min-w-0 flex-col gap-section">
                <CheckinBlockCard
                  config={checkinConfig}
                  rewards={twitchRewards}
                  loading={checkinLoading}
                  loadFailed={checkinLoadFailed}
                  isAffiliate={isAffiliate}
                  testing={previewMutation === 'checkin'}
                  open={expandedBlock === 'checkin'}
                  themeStatus={getThemePresentation('checkin').status}
                  themeChanged={
                    getThemePresentation('checkin').localDirty ||
                    Boolean(themeStates.checkin?.has_unpublished_changes)
                  }
                  onOpenChange={open => handleBlockOpenChange('checkin', open)}
                  onRetry={() => void loadCheckinTrigger()}
                  onTest={() => handleBlockPreview('checkin')}
                >
                  {renderThemeEditor('checkin')}
                </CheckinBlockCard>

                <TarotBlockCard
                  testing={previewMutation === 'tarot'}
                  open={expandedBlock === 'tarot'}
                  themeStatus={getThemePresentation('tarot').status}
                  themeChanged={
                    getThemePresentation('tarot').localDirty ||
                    Boolean(themeStates.tarot?.has_unpublished_changes)
                  }
                  onOpenChange={open => handleBlockOpenChange('tarot', open)}
                  onTest={() => handleBlockPreview('tarot')}
                >
                  {renderThemeEditor('tarot')}
                </TarotBlockCard>
              </div>
            </SlideUp>
          </section>

          <div
            data-layout-column="support"
            data-layout-position="fixed"
            className="flex min-w-0 flex-col gap-section xl:sticky xl:top-0 xl:col-span-4 xl:max-h-full xl:self-start xl:overflow-y-auto xl:overscroll-contain"
          >
            <section
              aria-labelledby="live-display-connection-title"
              data-layout-panel="connection"
              className="min-w-0"
            >
              <SlideUp data-layout-start="connection">
                <Card className="min-w-0">
                  <CardHeader className={CARD_HEADER_STACK_ON_MOBILE}>
                    <CardTitle className="flex flex-wrap items-center gap-2">
                      <h2 id="live-display-connection-title">OBS 連線</h2>
                      <Badge variant={access.enabled ? 'default' : 'outline'}>
                        {access.enabled ? '已啟用' : '已停用'}
                      </Badge>
                    </CardTitle>
                    <CardDescription>
                      將連結加入 OBS Browser Source，設定為 1920 × 1080、透明背景。
                    </CardDescription>
                    <CardAction>
                      <Switch
                        aria-label="啟用直播畫面顯示"
                        checked={access.enabled}
                        disabled={mutation !== null}
                        onCheckedChange={value => void handleEnabledChange(value)}
                      />
                    </CardAction>
                  </CardHeader>
                  <CardContent className="flex min-w-0 flex-col gap-card border-t pt-card">
                    <OverlayUrlBlock
                      url={overlayUrl}
                      copyLabel="點擊以複製 OBS 顯示連結"
                      openLabel="開啟 OBS 顯示畫面"
                    />
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button
                          variant="outline"
                          size="sm"
                          className="self-start"
                          disabled={mutation !== null}
                        >
                          {mutation === 'key' ? (
                            <Spinner className="mr-1.5" />
                          ) : (
                            <Icon icon="fa-solid fa-key" className="mr-1.5 text-label" />
                          )}
                          更新連結
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
                  </CardContent>
                </Card>
              </SlideUp>
            </section>

            <section
              aria-labelledby="live-display-preview-title"
              data-layout-panel="preview"
              className="min-w-0"
            >
              <SlideUp>
                <Card className="min-w-0">
                  <CardHeader>
                    <CardTitle className="flex flex-wrap items-center gap-2">
                      <h2 id="live-display-preview-title">預覽</h2>
                      <Badge variant="secondary">
                        {selectedBlock === 'checkin' ? '每日簽到' : '每日塔羅'}
                      </Badge>
                    </CardTitle>
                    <CardDescription>即時查看草稿與測試播放。</CardDescription>
                  </CardHeader>
                  <CardContent className="min-w-0 border-t pt-card">
                    {renderThemePreview(selectedBlock)}
                  </CardContent>
                </Card>
              </SlideUp>
            </section>
          </div>
        </div>
      )}
    </PageMain>
  )
}
