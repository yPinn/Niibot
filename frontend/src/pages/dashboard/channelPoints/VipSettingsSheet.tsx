import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import type { TwitchReward } from '@/api/events'
import {
  adjustVipEntitlement,
  adoptExternalVip,
  getVipState,
  initializeVipTracking,
  keepExternalVip,
  removeVipEntitlement,
  syncVipState,
  updateVipSlotLimit,
  upsertVipRule,
  type VipEntitlement,
  type VipState,
} from '@/api/vip'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { Icon, Spinner, TwitchRoleBadge } from '@/components/primitives'
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
  return entitlement.source === 'managed' ? '獎勵' : '外部'
}

function entitlementTermLabel(entitlement: VipEntitlement): string {
  if (entitlement.source !== 'managed') return '未納入期限管理'
  if (entitlement.is_permanent) return '永久'
  return formatRemaining(entitlement.expires_at)
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
  const [adjustingUserId, setAdjustingUserId] = useState<string | null>(null)
  const [adjustmentDuration, setAdjustmentDuration] = useState('3')
  const [removingEntitlement, setRemovingEntitlement] = useState<VipEntitlement | null>(null)

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
    <Sheet
      open={open}
      onOpenChange={nextOpen => {
        if (!nextOpen) {
          setAdjustingUserId(null)
          setRemovingEntitlement(null)
        }
        onOpenChange(nextOpen)
      }}
    >
      <SheetContent className="gap-section sm:max-w-4xl">
        <SheetHeader>
          <SheetTitle>VIP management</SheetTitle>
          <SheetDescription>設定 Reward 期限與管理目前的 VIP 名單。</SheetDescription>
        </SheetHeader>

        <div className="flex flex-1 flex-col overflow-y-auto px-page pb-page">
          {loading ? (
            <div className="grid gap-card lg:grid-cols-2">
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
            <div className="grid items-start gap-section lg:grid-cols-2">
              <div className="space-y-section">
                <section className="space-y-4" aria-labelledby="vip-capacity-title">
                  <div className="flex items-center justify-between gap-3">
                    <h3 id="vip-capacity-title" className="font-semibold">
                      VIP 使用量
                    </h3>
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
                  <p className="flex items-baseline gap-1.5 text-sub text-muted-foreground">
                    目前
                    <span className="text-card-title font-bold text-foreground tabular-nums">
                      {active.length}
                    </span>
                    位 VIP
                  </p>
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
                        {state.settings.tracking_started_at ? '儲存' : '清點並啟用'}
                      </Button>
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
                    <p className="text-label text-muted-foreground">修改期限只影響後續兌換。</p>
                  </div>
                  <div>
                    {state.rules.length === 0 ? (
                      <p className="rounded-md border border-dashed px-3 py-4 text-sub text-muted-foreground">
                        尚未設定 VIP Reward。
                      </p>
                    ) : (
                      <div className="divide-y rounded-md border">
                        {state.rules.map(rule => {
                          const currentDuration = ruleDurationValue(rule)
                          return (
                            <div
                              key={rule.reward_id}
                              className="grid items-center gap-2 px-3 py-2 sm:grid-cols-[minmax(0,1fr)_8rem_auto]"
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
                        })}
                      </div>
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
                        納入後會從現在起算期限，並於到期移除。
                      </p>
                    </div>
                    <div className="divide-y rounded-md border">
                      {pending.map(item => (
                        <div key={item.redemption_id} className="p-3">
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
                    </div>
                  </section>
                )}

                <section className="space-y-3" aria-labelledby="vip-list-title">
                  <h3 id="vip-list-title" className="font-semibold">
                    當前 VIP 名單
                  </h3>
                  {active.length === 0 ? (
                    <p className="rounded-md border border-dashed px-3 py-6 text-center text-sub text-muted-foreground">
                      Twitch 目前沒有 VIP，或尚未完成初次清點。
                    </p>
                  ) : (
                    <div className="divide-y rounded-md border">
                      {active.map(item => {
                        const displayName = item.display_name || item.user_login
                        const isAdjusting = adjustingUserId === item.user_id
                        return (
                          <div key={item.user_id} className="px-3 py-3">
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <TwitchRoleBadge role="vip" label="VIP" size={18} />
                                  <p className="truncate text-sub font-medium">{displayName}</p>
                                  <Badge variant="outline">{sourceLabel(item)}</Badge>
                                </div>
                                <p className="mt-1 text-label text-muted-foreground">
                                  {entitlementTermLabel(item)}
                                </p>
                              </div>
                              <div className="flex shrink-0 items-center gap-1">
                                {item.source === 'managed' && (
                                  <Button
                                    size="sm"
                                    variant="ghost"
                                    disabled={saving}
                                    aria-label={`調整 ${displayName} 期限`}
                                    onClick={() => {
                                      setAdjustingUserId(isAdjusting ? null : item.user_id)
                                      setAdjustmentDuration('3')
                                    }}
                                  >
                                    {isAdjusting ? '收合' : '調整'}
                                  </Button>
                                )}
                                <Button
                                  size="icon-sm"
                                  variant="ghost"
                                  disabled={saving}
                                  aria-label={`移除 ${displayName} 的 VIP`}
                                  title={`移除 ${displayName} 的 VIP`}
                                  className="text-muted-foreground hover:text-destructive"
                                  onClick={() => setRemovingEntitlement(item)}
                                >
                                  <Icon icon="fa-solid fa-user-xmark" wrapperClassName="size-4" />
                                </Button>
                              </div>
                            </div>
                            {isAdjusting && (
                              <div className="mt-3 flex flex-wrap items-center justify-end gap-2 border-t pt-3">
                                <Select
                                  value={adjustmentDuration}
                                  onValueChange={setAdjustmentDuration}
                                >
                                  <SelectTrigger
                                    className="w-32"
                                    aria-label={`調整 ${displayName} 期限`}
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
                                <Button
                                  size="sm"
                                  variant="outline"
                                  disabled={saving}
                                  onClick={() => setAdjustingUserId(null)}
                                >
                                  取消
                                </Button>
                                <Button
                                  size="sm"
                                  disabled={saving}
                                  onClick={async () => {
                                    const duration = durationPayload(adjustmentDuration)
                                    const succeeded = await runMutation(
                                      () =>
                                        adjustVipEntitlement(
                                          item.user_id,
                                          duration.months,
                                          duration.permanent
                                        ),
                                      'VIP 預計期限已調整'
                                    )
                                    if (succeeded) setAdjustingUserId(null)
                                  }}
                                >
                                  套用
                                </Button>
                              </div>
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
                      請由實況主或 Moderator 在 Twitch 人工退款。
                    </p>
                    <div className="divide-y rounded-md border">
                      {failures.slice(0, 10).map(item => (
                        <div key={item.redemption_id} className="px-3 py-2 text-sub">
                          <p className="font-medium">{item.display_name || item.user_login}</p>
                          <p className="text-label text-muted-foreground">
                            {item.reward_name_snapshot} ·{' '}
                            {failureLabel(item.error_code, item.status)}
                          </p>
                        </div>
                      ))}
                    </div>
                  </section>
                )}
              </div>
            </div>
          )}
        </div>
        <DeleteConfirmDialog
          open={removingEntitlement !== null}
          onOpenChange={nextOpen => {
            if (!nextOpen) setRemovingEntitlement(null)
          }}
          title={`移除 ${
            removingEntitlement?.display_name || removingEntitlement?.user_login || '這位使用者'
          } 的 VIP？`}
          description="這會立即從 Twitch 撤銷 VIP，並結束 Niibot 對目前期限的管理。之後新的有效兌換仍可再次授予 VIP。"
          actionLabel="移除 VIP"
          onConfirm={() => {
            if (!removingEntitlement) return
            const entitlement = removingEntitlement
            const displayName = entitlement.display_name || entitlement.user_login
            void runMutation(
              () => removeVipEntitlement(entitlement.user_id),
              `${displayName} 的 Twitch VIP 已移除`
            )
          }}
        />
      </SheetContent>
    </Sheet>
  )
}
