import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { TwitchReward } from '@/api/events'
import {
  adjustVipEntitlement,
  adoptExternalVip,
  getVipState,
  initializeVipTracking,
  keepExternalVip,
  syncVipState,
  updateVipSlotLimit,
  upsertVipRule,
  type VipEntitlement,
  type VipState,
} from '@/api/vip'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Switch,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

interface VipSettingsSheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  twitchRewards: TwitchReward[]
  onRulesChanged: (rules: VipState['rules']) => void
}

const DURATION_OPTIONS = [
  { value: '1', label: '1 個月' },
  { value: '3', label: '3 個月' },
  { value: '6', label: '6 個月' },
  { value: '12', label: '1 年' },
  { value: 'permanent', label: '永久' },
] as const

function formatDate(value: string | null): string {
  if (!value) return '—'
  return new Intl.DateTimeFormat('zh-TW', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value))
}

function durationPayload(value: string) {
  return value === 'permanent'
    ? { months: null, permanent: true }
    : { months: Number(value), permanent: false }
}

function ruleDurationValue(rule: VipState['rules'][number]): string {
  return rule.is_permanent ? 'permanent' : String(rule.duration_months ?? 3)
}

function durationOptions(currentValue?: string) {
  if (!currentValue || DURATION_OPTIONS.some(option => option.value === currentValue)) {
    return DURATION_OPTIONS
  }
  return [
    ...DURATION_OPTIONS,
    { value: currentValue, label: `${currentValue} 個月` },
  ] as ReadonlyArray<{ value: string; label: string }>
}

function formatRemaining(value: string | null): string {
  if (!value) return '—'
  const remainingMs = new Date(value).getTime() - Date.now()
  if (remainingMs <= 0) return '已到期，等待同步'
  const remainingHours = Math.ceil(remainingMs / (60 * 60 * 1000))
  if (remainingHours < 24) return `剩餘 ${remainingHours} 小時`
  return `剩餘 ${Math.ceil(remainingHours / 24)} 天`
}

const FAILURE_LABELS: Record<string, string> = {
  vip_tracking_not_initialized: '尚未完成 VIP 初次清點',
  vip_capacity_full: 'Niibot 設定的 VIP 名額已滿',
  twitch_vip_capacity_full: 'Twitch VIP 名額已滿',
  twitch_user_is_moderator: '該使用者為 Moderator，Twitch 不允許授予 VIP',
  twitch_vip_grant_failed: 'Twitch 授予 VIP 失敗',
  vip_rule_missing_during_recovery: '找不到原兌換規則，無法完成復原',
  twitch_vip_grant_not_observed: 'Twitch 未確認 VIP 已授予',
  vip_duration_missing_during_recovery: '原期限資料不完整，無法完成復原',
  capacity_full: 'VIP 名額已滿',
  moderator_conflict: '該使用者為 Moderator，無法授予 VIP',
  not_initialized: '尚未完成 VIP 初次清點',
  failed: 'Twitch 授予 VIP 失敗',
}

function failureLabel(errorCode: string | null, status: string): string {
  return (
    (errorCode && FAILURE_LABELS[errorCode]) ||
    FAILURE_LABELS[status] ||
    '兌換未完成，請檢查 Twitch 狀態'
  )
}

function sourceLabel(entitlement: VipEntitlement): string {
  if (entitlement.source === 'managed') return 'Niibot 管理'
  if (entitlement.source === 'external_baseline') return '初次清點'
  return 'Twitch 外部'
}

export function VipSettingsSheet({
  open,
  onOpenChange,
  twitchRewards,
  onRulesChanged,
}: VipSettingsSheetProps) {
  const [state, setState] = useState<VipState | null>(null)
  const [loading, setLoading] = useState(false)
  const [loadFailed, setLoadFailed] = useState(false)
  const [saving, setSaving] = useState(false)
  const [slotLimit, setSlotLimit] = useState('')
  const [rewardId, setRewardId] = useState('')
  const [ruleDuration, setRuleDuration] = useState('3')
  const [adjustments, setAdjustments] = useState<Record<string, string>>({})

  const loadState = useCallback(async () => {
    setLoading(true)
    setLoadFailed(false)
    try {
      const next = await getVipState()
      setState(next)
      onRulesChanged(next.rules)
      setSlotLimit(next.settings.slot_limit?.toString() ?? '')
    } catch (error) {
      setLoadFailed(true)
      toastApiError(error, '載入 VIP 管理資料失敗')
    } finally {
      setLoading(false)
    }
  }, [onRulesChanged])

  useEffect(() => {
    if (!open) return
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadState()
  }, [loadState, open])

  const active = useMemo(
    () => state?.entitlements.filter(item => item.status === 'active') ?? [],
    [state]
  )
  const managedCount = active.filter(item => item.source === 'managed').length
  const externalCount = active.length - managedCount
  const available =
    state?.settings.slot_limit == null
      ? null
      : Math.max(state.settings.slot_limit - active.length, 0)
  const pending =
    state?.redemptions.filter(item => item.status === 'needs_review_external_vip') ?? []
  const failures =
    state?.redemptions.filter(item =>
      ['capacity_full', 'moderator_conflict', 'failed', 'not_initialized'].includes(item.status)
    ) ?? []
  const unboundRewards = twitchRewards.filter(
    reward => !state?.rules.some(rule => rule.reward_id === reward.id)
  )

  const runMutation = async (
    operation: () => Promise<unknown>,
    success: string
  ): Promise<boolean> => {
    setSaving(true)
    try {
      await operation()
      toast.success(success)
      await loadState()
      return true
    } catch (error) {
      toastApiError(error, success.replace('已', '') + '失敗')
      return false
    } finally {
      setSaving(false)
    }
  }

  const parsedLimit = Number(slotLimit)
  const validLimit = Number.isInteger(parsedLimit) && parsedLimit >= 1 && parsedLimit <= 500

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="gap-section sm:max-w-5xl">
        <SheetHeader>
          <SheetTitle>VIP management</SheetTitle>
          <SheetDescription>
            清點 Twitch 真實 VIP、管理多個 Reward 的計畫期限，並處理外部 VIP 與失敗兌換。
          </SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col overflow-y-auto px-page pb-page">
          {loading ? (
            <div className="grid gap-card lg:grid-cols-[minmax(18rem,0.9fr)_minmax(24rem,1.4fr)]">
              <Skeleton className="h-96 w-full" />
              <Skeleton className="h-96 w-full" />
            </div>
          ) : loadFailed || !state ? (
            <Alert variant="destructive">
              <Icon icon="fa-solid fa-circle-exclamation" />
              <AlertTitle>VIP 管理資料載入失敗</AlertTitle>
              <AlertDescription>
                <Button size="sm" variant="outline" onClick={() => void loadState()}>
                  重新載入
                </Button>
              </AlertDescription>
            </Alert>
          ) : (
            <div className="grid items-start gap-section lg:grid-cols-[minmax(18rem,0.9fr)_minmax(24rem,1.4fr)]">
              <div className="space-y-section">
                <section className="space-y-4" aria-labelledby="vip-capacity-title">
                  <div className="space-y-1">
                    <h3 id="vip-capacity-title" className="font-semibold">
                      容量與同步
                    </h3>
                    <p className="text-label text-muted-foreground">
                      上限為人工設定的預檢值；Twitch Grant 結果仍是最終判定。
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sub sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4">
                    {[
                      ['實際', active.length],
                      ['可用', available ?? '—'],
                      ['Managed', managedCount],
                      ['External', externalCount],
                    ].map(([label, value]) => (
                      <div key={label} className="rounded-md border bg-muted/30 px-3 py-2">
                        <p className="text-label text-muted-foreground">{label}</p>
                        <p className="mt-1 font-medium tabular-nums">{value}</p>
                      </div>
                    ))}
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="vip-slot-limit">VIP 上限</Label>
                    <div className="flex gap-2">
                      <Input
                        id="vip-slot-limit"
                        type="number"
                        min={1}
                        max={500}
                        value={slotLimit}
                        onChange={event => setSlotLimit(event.target.value)}
                      />
                      <Button
                        disabled={!validLimit || saving}
                        onClick={() =>
                          void runMutation(
                            () =>
                              state.settings.tracking_started_at
                                ? updateVipSlotLimit(parsedLimit)
                                : initializeVipTracking(parsedLimit),
                            state.settings.tracking_started_at ? 'VIP 上限已更新' : 'VIP 清點已完成'
                          )
                        }
                      >
                        {saving && <Spinner className="mr-1.5" />}
                        {state.settings.tracking_started_at ? '更新' : '清點並啟用'}
                      </Button>
                    </div>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-label text-muted-foreground">
                        上次完整同步：{formatDate(state.settings.last_full_sync_at)}
                      </p>
                      {state.settings.tracking_started_at && (
                        <Button
                          size="sm"
                          variant="ghost"
                          disabled={saving}
                          onClick={() =>
                            void runMutation(() => syncVipState(), 'Twitch VIP 名單已重新清點')
                          }
                        >
                          重新清點
                        </Button>
                      )}
                    </div>
                  </div>
                </section>

                <section
                  className="space-y-4 border-t pt-section"
                  aria-labelledby="vip-rules-title"
                >
                  <div className="space-y-1">
                    <h3 id="vip-rules-title" className="font-semibold">
                      Reward 期限規則
                    </h3>
                    <p className="text-label text-muted-foreground">
                      新規則預設三個 calendar months；修改只影響後續兌換。
                    </p>
                  </div>
                  <div className="space-y-2">
                    {state.rules.length === 0 ? (
                      <p className="rounded-md border border-dashed px-3 py-4 text-sub text-muted-foreground">
                        尚未設定 VIP Reward。
                      </p>
                    ) : (
                      state.rules.map(rule => {
                        const currentDuration = ruleDurationValue(rule)
                        return (
                          <div
                            key={rule.reward_id}
                            className="grid items-center gap-2 rounded-md border px-3 py-2 sm:grid-cols-[minmax(0,1fr)_8rem_auto]"
                          >
                            <p className="min-w-0 truncate text-sub font-medium">
                              {rule.reward_name_snapshot}
                            </p>
                            <Select
                              value={currentDuration}
                              disabled={saving}
                              onValueChange={value => {
                                const duration = durationPayload(value)
                                void runMutation(
                                  () =>
                                    upsertVipRule(rule.reward_id, {
                                      duration_months: duration.months,
                                      is_permanent: duration.permanent,
                                      enabled: rule.enabled,
                                    }),
                                  'VIP Reward 期限已更新'
                                )
                              }}
                            >
                              <SelectTrigger aria-label={`${rule.reward_name_snapshot} 的期限`}>
                                <SelectValue />
                              </SelectTrigger>
                              <SelectContent>
                                {durationOptions(currentDuration).map(option => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Switch
                              checked={rule.enabled}
                              disabled={saving}
                              aria-label={`啟用 ${rule.reward_name_snapshot}`}
                              onCheckedChange={enabled =>
                                void runMutation(
                                  () =>
                                    upsertVipRule(rule.reward_id, {
                                      duration_months: rule.duration_months,
                                      is_permanent: rule.is_permanent,
                                      enabled,
                                    }),
                                  enabled ? 'VIP Reward 規則已啟用' : 'VIP Reward 規則已停用'
                                )
                              }
                            />
                          </div>
                        )
                      })
                    )}
                  </div>
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_8rem_auto] lg:grid-cols-1 xl:grid-cols-[minmax(0,1fr)_8rem_auto]">
                    <Select value={rewardId} onValueChange={setRewardId}>
                      <SelectTrigger aria-label="新增 VIP Reward">
                        <SelectValue placeholder="選擇 Twitch Reward" />
                      </SelectTrigger>
                      <SelectContent>
                        {unboundRewards.map(reward => (
                          <SelectItem key={reward.id} value={reward.id}>
                            {reward.title} ({reward.cost.toLocaleString()} 點)
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Select value={ruleDuration} onValueChange={setRuleDuration}>
                      <SelectTrigger aria-label="VIP 計畫期限">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DURATION_OPTIONS.map(option => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <Button
                      variant="outline"
                      disabled={!rewardId || saving}
                      onClick={async () => {
                        const duration = durationPayload(ruleDuration)
                        const succeeded = await runMutation(
                          () =>
                            upsertVipRule(rewardId, {
                              duration_months: duration.months,
                              is_permanent: duration.permanent,
                              enabled: true,
                            }),
                          'VIP Reward 規則已新增'
                        )
                        if (succeeded) setRewardId('')
                      }}
                    >
                      新增
                    </Button>
                  </div>
                </section>
              </div>

              <div className="space-y-section lg:border-l lg:pl-section">
                {pending.length > 0 && (
                  <section className="space-y-3" aria-labelledby="vip-review-title">
                    <div className="space-y-1">
                      <h3 id="vip-review-title" className="font-semibold">
                        待人工確認
                      </h3>
                      <p className="text-label text-muted-foreground">
                        使用者原本已是外部 VIP；納入後將從現在起算完整期限並於到期自動移除。
                      </p>
                    </div>
                    {pending.map(item => (
                      <div key={item.redemption_id} className="rounded-md border p-3">
                        <div className="flex flex-wrap items-start justify-between gap-2">
                          <div>
                            <p className="font-medium">{item.display_name || item.user_login}</p>
                            <p className="text-label text-muted-foreground">
                              {item.reward_name_snapshot}
                            </p>
                          </div>
                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              disabled={saving}
                              onClick={() =>
                                void runMutation(
                                  () =>
                                    adoptExternalVip(
                                      item.redemption_id,
                                      item.duration_months_snapshot,
                                      item.is_permanent_snapshot
                                    ),
                                  '外部 VIP 已納入期限管理'
                                )
                              }
                            >
                              納入管理
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              disabled={saving}
                              onClick={() =>
                                void runMutation(
                                  () => keepExternalVip(item.redemption_id),
                                  '已保留為外部 VIP，請至 Twitch 人工退款'
                                )
                              }
                            >
                              保持外部
                            </Button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </section>
                )}

                <section className="space-y-3" aria-labelledby="vip-list-title">
                  <div className="space-y-1">
                    <h3 id="vip-list-title" className="font-semibold">
                      當前 VIP 名單
                    </h3>
                    <p className="text-label text-muted-foreground">
                      顯示 Twitch 實際狀態、來源與 Niibot 計畫期限；手動移除會在下次同步清理。
                    </p>
                  </div>
                  {active.length === 0 ? (
                    <p className="rounded-md border border-dashed px-3 py-6 text-center text-sub text-muted-foreground">
                      Twitch 目前沒有 VIP，或尚未完成初次清點。
                    </p>
                  ) : (
                    <div className="divide-y rounded-md border">
                      {active.map(item => {
                        const selection = adjustments[item.user_id] ?? '3'
                        return (
                          <div
                            key={item.user_id}
                            className="grid gap-2 px-3 py-3 sm:grid-cols-[minmax(0,1fr)_9rem_auto] sm:items-center"
                          >
                            <div className="min-w-0">
                              <div className="flex flex-wrap items-center gap-2">
                                <p className="truncate text-sub font-medium">
                                  {item.display_name || item.user_login}
                                </p>
                                <Badge variant="outline">{sourceLabel(item)}</Badge>
                              </div>
                              <p className="mt-1 text-label text-muted-foreground">
                                預計到期：
                                {item.is_permanent ? '永久' : formatDate(item.expires_at)}
                                {!item.is_permanent && `（${formatRemaining(item.expires_at)}）`}
                              </p>
                            </div>
                            {item.source === 'managed' ? (
                              <Select
                                value={selection}
                                onValueChange={value =>
                                  setAdjustments(current => ({ ...current, [item.user_id]: value }))
                                }
                              >
                                <SelectTrigger
                                  aria-label={`調整 ${item.display_name || item.user_login} 期限`}
                                >
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {DURATION_OPTIONS.map(option => (
                                    <SelectItem key={option.value} value={option.value}>
                                      {option.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <span />
                            )}
                            {item.source === 'managed' && (
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={saving}
                                onClick={() => {
                                  const duration = durationPayload(selection)
                                  void runMutation(
                                    () =>
                                      adjustVipEntitlement(
                                        item.user_id,
                                        duration.months,
                                        duration.permanent
                                      ),
                                    'VIP 預計期限已調整'
                                  )
                                }}
                              >
                                調整
                              </Button>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </section>

                {failures.length > 0 && (
                  <section
                    className="space-y-3 border-t pt-section"
                    aria-labelledby="vip-failures-title"
                  >
                    <h3 id="vip-failures-title" className="font-semibold">
                      需退款／處理
                    </h3>
                    <p className="text-label text-muted-foreground">
                      Niibot 不會自動退款；請由實況主或 Moderator 在 Twitch 完成人工退款。
                    </p>
                    <div className="space-y-2">
                      {failures.slice(0, 10).map(item => (
                        <div
                          key={item.redemption_id}
                          className="flex items-start justify-between gap-3 rounded-md border px-3 py-2 text-sub"
                        >
                          <div>
                            <p className="font-medium">{item.display_name || item.user_login}</p>
                            <p className="text-label text-muted-foreground">
                              {item.reward_name_snapshot} ·{' '}
                              {failureLabel(item.error_code, item.status)}
                            </p>
                          </div>
                          <Badge variant="destructive">人工退款</Badge>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  )
}
