import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  type TwitchReward,
  updateRedemptionConfig,
} from '@/api/events'
import { getVipState, setVipRulesEnabled, type VipRewardRule } from '@/api/vip'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { SlideUp } from '@/components/primitives'
import { Alert, AlertDescription, AlertTitle, Button } from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useSortState } from '@/hooks/useSortState'
import { applyDir } from '@/lib/sort'
import { toastApiError } from '@/lib/toast-error'

import { ChannelPointActionsTable, type ChannelPointSortKey } from './ChannelPointActionsTable'
import { CheckinSettingsSheet } from './CheckinSettingsSheet'
import { ACTION_TYPE_DEFAULT_ORDER, ACTION_TYPE_LABELS } from './constants'
import { VipSettingsSheet } from './VipSettingsSheet'

const ACTION_TYPE_ORDER = new Map<string, number>(
  ACTION_TYPE_DEFAULT_ORDER.map((actionType, index) => [actionType, index])
)

export default function ChannelPoints() {
  useDocumentTitle('Channel Points')
  const { isAffiliate } = useAuth()
  const [redemptions, setRedemptions] = useState<RedemptionConfig[]>([])
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)
  const [loadFailed, setLoadFailed] = useState(false)
  const [checkinSettingsOpen, setCheckinSettingsOpen] = useState(false)
  const [vipSettingsOpen, setVipSettingsOpen] = useState(false)
  const [vipRules, setVipRules] = useState<VipRewardRule[]>([])
  const sort = useSortState<ChannelPointSortKey>('action_type')

  const loadChannelPoints = useCallback(async () => {
    setLoadFailed(false)
    setRedemptionLoading(true)
    setRewardsLoading(true)
    const configsPromise = getRedemptionConfigs()
    const rewardsPromise = isAffiliate ? getTwitchRewards() : Promise.resolve([] as TwitchReward[])
    const vipStatePromise = isAffiliate ? getVipState() : Promise.resolve(null)

    try {
      const configs = await configsPromise
      setRedemptions(configs.filter(config => config.action_type !== 'niibot_auth'))
    } catch {
      setLoadFailed(true)
    } finally {
      setRedemptionLoading(false)
    }

    try {
      const rewards = await rewardsPromise
      setTwitchRewards([...rewards].sort((left, right) => left.cost - right.cost))
    } catch {
      setLoadFailed(true)
    } finally {
      setRewardsLoading(false)
    }

    try {
      const vipState = await vipStatePromise
      setVipRules(vipState?.rules ?? [])
    } catch {
      setLoadFailed(true)
    }
  }, [isAffiliate])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadChannelPoints()
  }, [loadChannelPoints])

  const sortedRedemptions = useMemo(() => {
    return [...redemptions].sort((left, right) => {
      let comparison = 0
      switch (sort.sortKey) {
        case 'action_type':
          comparison =
            (ACTION_TYPE_ORDER.get(left.action_type) ?? Number.MAX_SAFE_INTEGER) -
              (ACTION_TYPE_ORDER.get(right.action_type) ?? Number.MAX_SAFE_INTEGER) ||
            (ACTION_TYPE_LABELS[left.action_type] ?? left.action_type).localeCompare(
              ACTION_TYPE_LABELS[right.action_type] ?? right.action_type
            )
          break
        case 'reward_name':
          comparison = left.reward_name.localeCompare(right.reward_name)
          break
        case 'enabled':
          comparison =
            Number(
              left.action_type === 'vip' ? vipRules.some(rule => rule.enabled) : left.enabled
            ) -
            Number(
              right.action_type === 'vip' ? vipRules.some(rule => rule.enabled) : right.enabled
            )
          break
      }
      return applyDir(comparison, sort.sortDir)
    })
  }, [redemptions, sort.sortDir, sort.sortKey, vipRules])

  const { toggle: handleToggle } = useOptimisticToggle<RedemptionConfig>({
    setState: setRedemptions,
    getId: redemption => redemption.action_type,
    toggleFn: (redemption, enabled) =>
      updateRedemptionConfig(redemption.action_type, {
        reward_id: redemption.reward_id,
        reward_name: redemption.reward_name,
        enabled,
      }).then(() => {}),
    messages: {
      on: '頻道點數動作已啟用',
      off: '頻道點數動作已停用',
      error: '切換頻道點數動作失敗',
    },
  })

  const handleRewardSelect = async (redemption: RedemptionConfig, rewardId: string) => {
    const reward = twitchRewards.find(item => item.id === rewardId)
    try {
      const updated = await updateRedemptionConfig(redemption.action_type, {
        reward_id: reward?.id ?? null,
        reward_name: reward?.title ?? '',
        enabled: reward ? redemption.enabled : false,
      })
      setRedemptions(current =>
        current.map(item => (item.action_type === updated.action_type ? updated : item))
      )
      toast.success(reward ? 'Twitch 獎勵已綁定' : 'Twitch 獎勵已解除')
    } catch (error) {
      toastApiError(error, '更新 Twitch 獎勵失敗')
    }
  }

  const handleVipToggle = async () => {
    const nextEnabled = !vipRules.some(rule => rule.enabled)
    const previous = vipRules
    setVipRules(current => current.map(rule => ({ ...rule, enabled: nextEnabled })))
    try {
      setVipRules(await setVipRulesEnabled(nextEnabled))
      toast.success(nextEnabled ? 'VIP Reward 規則已啟用' : 'VIP Reward 規則已停用')
    } catch (error) {
      setVipRules(previous)
      toastApiError(error, '切換 VIP Reward 規則失敗')
    }
  }

  return (
    <PageMain>
      <PageHeader
        title="Channel Points"
        description="管理 Twitch 自訂獎勵與 Niibot 功能的對應關係。"
      />

      {loadFailed && (
        <Alert variant="destructive">
          <AlertTitle>部分頻道點數設定載入失敗</AlertTitle>
          <AlertDescription className="flex flex-wrap items-center justify-between gap-3">
            <span>既有資料仍會保留；請重新載入後再進行修改。</span>
            <Button size="sm" variant="outline" onClick={() => void loadChannelPoints()}>
              重新載入
            </Button>
          </AlertDescription>
        </Alert>
      )}

      <SlideUp inView>
        <ChannelPointActionsTable
          redemptions={sortedRedemptions}
          twitchRewards={twitchRewards}
          redemptionLoading={redemptionLoading}
          rewardsLoading={rewardsLoading}
          sort={sort}
          isAffiliate={isAffiliate}
          onToggle={handleToggle}
          onRewardSelect={(redemption, rewardId) => void handleRewardSelect(redemption, rewardId)}
          onEditCheckinSettings={() => setCheckinSettingsOpen(true)}
          onEditVipSettings={() => setVipSettingsOpen(true)}
          vipRules={vipRules}
          onToggleVip={() => void handleVipToggle()}
        />
      </SlideUp>

      <CheckinSettingsSheet open={checkinSettingsOpen} onOpenChange={setCheckinSettingsOpen} />
      <VipSettingsSheet
        open={vipSettingsOpen}
        onOpenChange={setVipSettingsOpen}
        twitchRewards={twitchRewards}
        onRulesChanged={setVipRules}
      />
    </PageMain>
  )
}
