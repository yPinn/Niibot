import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type AdminChannel,
  approveActivationRequest,
  type BotTokenInfo,
  getAdminBotStatus,
  getAdminChannels,
  reinstateMembership,
  rejectActivationRequest,
  suspendMembership,
} from '@/api/admin'
import {
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  type TwitchReward,
  updateRedemptionConfig,
} from '@/api/events'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { EmptyState, Icon, SlideUp } from '@/components/primitives'
import { Button, Card, CardContent, CardHeader, CardTitle, Skeleton } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import { type ChannelCategory as ChannelCategoryValue, getChannelCategory } from './channelStatus'
import { ActivationCodes } from './components/ActivationCodes'
import { BotStatusPanel } from './components/BotStatusPanel'
import { ChannelCard } from './components/ChannelCard'

type ChannelFilterValue = 'all' | ChannelCategoryValue

interface ChannelCategoryDefinition {
  value: ChannelCategoryValue
  label: string
  icon: string
  toneClassName: string
}

// Actionable groups lead so the operator's to-do list is the first thing seen.
const CHANNEL_CATEGORY_DEFINITIONS: ChannelCategoryDefinition[] = [
  {
    value: 'issues',
    label: '需處理',
    icon: 'fa-solid fa-triangle-exclamation',
    toneClassName: 'text-status-warning',
  },
  {
    value: 'pending',
    label: '待審核',
    icon: 'fa-solid fa-hourglass-half',
    toneClassName: 'text-status-info',
  },
  {
    value: 'healthy',
    label: '正常監聽',
    icon: 'fa-solid fa-shield-check',
    toneClassName: 'text-status-online',
  },
  {
    value: 'paused',
    label: '監控暫停',
    icon: 'fa-solid fa-circle-pause',
    toneClassName: 'text-muted-foreground',
  },
  {
    value: 'suspended',
    label: '已停權',
    icon: 'fa-solid fa-ban',
    toneClassName: 'text-destructive',
  },
]

function sortCategoryChannels(channels: AdminChannel[]): AdminChannel[] {
  return [...channels].sort((a, b) => {
    if (a.is_live !== b.is_live) return a.is_live ? -1 : 1
    return a.display_name.localeCompare(b.display_name, 'zh-Hant', { sensitivity: 'base' })
  })
}

export default function AdminPage() {
  useDocumentTitle('Admin')

  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)
  const [channelFilter, setChannelFilter] = useState<ChannelFilterValue>('all')

  const channelCategories = useMemo(() => {
    const buckets = new Map<ChannelCategoryValue, AdminChannel[]>(
      CHANNEL_CATEGORY_DEFINITIONS.map(category => [category.value, []])
    )

    channels.forEach(channel => {
      if (!channel.is_bot) buckets.get(getChannelCategory(channel))?.push(channel)
    })

    return CHANNEL_CATEGORY_DEFINITIONS.map(category => ({
      ...category,
      channels: sortCategoryChannels(buckets.get(category.value) ?? []),
    }))
  }, [channels])

  const allUserChannels = channelCategories.flatMap(category => category.channels)
  const nonEmptyCategories = channelCategories.filter(category => category.channels.length > 0)
  // A filter whose last channel was just resolved falls back to "all"
  // instead of leaving an empty view behind.
  const activeFilter = nonEmptyCategories.some(category => category.value === channelFilter)
    ? channelFilter
    : 'all'
  const visibleCategories =
    activeFilter === 'all'
      ? nonEmptyCategories
      : nonEmptyCategories.filter(category => category.value === activeFilter)
  const channelFilters = [
    { value: 'all' as const, label: '全部', count: allUserChannels.length },
    ...nonEmptyCategories.map(category => ({
      value: category.value,
      label: category.label,
      count: category.channels.length,
    })),
  ]

  const [botStatus, setBotStatus] = useState<BotTokenInfo | null>(null)
  const [botLoading, setBotLoading] = useState(true)

  const [niibotAuth, setNiibotAuth] = useState<RedemptionConfig | null>(null)
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)

  useEffect(() => {
    getAdminChannels()
      .then(setChannels)
      .catch(() => setChannels([]))
      .finally(() => setChannelsLoading(false))

    getAdminBotStatus()
      .then(setBotStatus)
      .catch(() => setBotStatus(null))
      .finally(() => setBotLoading(false))

    getRedemptionConfigs()
      .then(configs => setNiibotAuth(configs.find(r => r.action_type === 'niibot_auth') ?? null))
      .catch(() => setNiibotAuth(null))
      .finally(() => setRedemptionLoading(false))

    getTwitchRewards()
      .then(rewards => setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost)))
      .catch(() => setTwitchRewards([]))
      .finally(() => setRewardsLoading(false))
  }, [])

  const handleRewardSelect = async (rewardId: string) => {
    if (!niibotAuth) return
    const reward = twitchRewards.find(item => item.id === rewardId)
    try {
      const updated = await updateRedemptionConfig('niibot_auth', {
        reward_id: reward?.id ?? null,
        reward_name: reward?.title ?? '',
        enabled: reward ? niibotAuth.enabled : false,
      })
      setNiibotAuth(updated)
      toast.success('Niibot 授權獎勵已更新')
    } catch (e) {
      toastApiError(e, '更新失敗')
    }
  }

  const refreshChannels = () =>
    getAdminChannels()
      .then(setChannels)
      .catch(() => undefined)

  /** Runs a membership transition, then refetches rather than patching
   * locally: approve/reinstate flip channels.enabled server-side (084's
   * trigger) and re-derive mod_status, which the client can't compute. A
   * failed refresh must not read as a failed transition, so it's separate. */
  const commitMembership = async (
    ch: AdminChannel,
    mutate: (userId: string) => Promise<void>,
    successMessage: string,
    errorMessage: string
  ): Promise<boolean> => {
    if (!ch.owner_user_id) return false
    try {
      await mutate(ch.owner_user_id)
    } catch (e) {
      toastApiError(e, errorMessage)
      return false
    }
    toast.success(successMessage)
    await refreshChannels()
    return true
  }

  const handleReinstate = (ch: AdminChannel) =>
    commitMembership(
      ch,
      id => reinstateMembership(id, 'admin_reinstate'),
      `${ch.display_name} 授權已恢復`,
      '恢復失敗'
    )

  const handleApprove = (ch: AdminChannel) =>
    commitMembership(ch, approveActivationRequest, `${ch.display_name} 已通過`, '審核失敗')

  const handleReject = (ch: AdminChannel) =>
    commitMembership(ch, rejectActivationRequest, `${ch.display_name} 的申請已拒絕`, '操作失敗')

  const handleSuspend = async (ch: AdminChannel, reason: string): Promise<boolean> => {
    if (!ch.owner_user_id) return false
    try {
      await suspendMembership(ch.owner_user_id, reason)
    } catch (e) {
      toastApiError(e, '停權失敗')
      return false
    }

    // The mutation is already committed. Reflect that result immediately so a
    // transient list refresh failure cannot be mistaken for a failed suspension.
    setChannels(current =>
      current.map(item =>
        item.owner_user_id === ch.owner_user_id
          ? {
              ...item,
              is_enabled: false,
              membership_status: 'suspended',
              membership_reason: reason,
            }
          : item
      )
    )
    toast.success(`${ch.display_name} 已停權`)

    // Reconcile trigger-derived fields in the background while preserving the
    // locally committed state if this non-critical refresh is unavailable.
    void refreshChannels()
    return true
  }

  const handleAuthToggle = async () => {
    if (!niibotAuth) return
    const newEnabled = !niibotAuth.enabled
    setNiibotAuth(prev => (prev ? { ...prev, enabled: newEnabled } : prev))
    try {
      const updated = await updateRedemptionConfig('niibot_auth', {
        reward_id: niibotAuth.reward_id,
        reward_name: niibotAuth.reward_name,
        enabled: newEnabled,
      })
      setNiibotAuth(updated)
    } catch (e) {
      setNiibotAuth(prev => (prev ? { ...prev, enabled: !newEnabled } : prev))
      toastApiError(e, '切換狀態失敗')
    }
  }

  return (
    <PageMain className="lg:gap-card">
      <PageHeader title="Admin" description="管理使用者授權、監控頻道與 Bot 狀態。" />

      <div className="grid grid-cols-1 gap-card items-start lg:grid-cols-[minmax(0,1fr)_360px]">
        <SlideUp>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-element">
                <Icon
                  icon="fa-brands fa-twitch"
                  size="sm"
                  wrapperClassName="text-muted-foreground"
                />
                <CardTitle role="heading" aria-level={2} className="text-card-title">
                  使用者與頻道
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              {channelsLoading ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-video w-full rounded-lg" />
                  ))}
                </div>
              ) : allUserChannels.length === 0 ? (
                <EmptyState icon="fa-solid fa-users" title="尚無使用者頻道" />
              ) : (
                <div className="space-y-section">
                  <div
                    className="flex flex-wrap items-center gap-element"
                    role="group"
                    aria-label="使用者狀態篩選"
                  >
                    {channelFilters.map(filter => {
                      const active = activeFilter === filter.value
                      return (
                        <Button
                          key={filter.value}
                          type="button"
                          size="sm"
                          variant={active ? 'default' : 'outline'}
                          onClick={() => setChannelFilter(filter.value)}
                          aria-pressed={active}
                        >
                          {filter.label}
                          <span className="font-mono text-label opacity-75">{filter.count}</span>
                        </Button>
                      )
                    })}
                  </div>

                  <div className="space-y-card">
                    {visibleCategories.map(category => (
                      // The filter chip already names a single selected group, so
                      // the heading only earns its space in the mixed "all" view.
                      <section
                        key={category.value}
                        aria-label={category.label}
                        className="space-y-section"
                      >
                        {activeFilter === 'all' && (
                          <div className="flex items-center gap-element border-b pb-element">
                            <Icon
                              icon={category.icon}
                              size="xs"
                              wrapperClassName={category.toneClassName}
                            />
                            <h3 className="text-sub font-semibold">{category.label}</h3>
                          </div>
                        )}

                        <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                          {category.channels.map(ch => (
                            <ChannelCard
                              key={ch.id}
                              ch={ch}
                              onSuspend={
                                ch.membership_status === 'active' ? handleSuspend : undefined
                              }
                              onReinstate={
                                ch.membership_status === 'suspended' ? handleReinstate : undefined
                              }
                              onApprove={
                                ch.membership_status === 'pending' ? handleApprove : undefined
                              }
                              onReject={
                                ch.membership_status === 'pending' ? handleReject : undefined
                              }
                              onRecheck={refreshChannels}
                            />
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </SlideUp>

        <div className="flex flex-col gap-card">
          <SlideUp delay={0.1}>
            <BotStatusPanel
              bot={botStatus}
              botLoading={botLoading}
              redemptionLoading={redemptionLoading}
              rewardsLoading={rewardsLoading}
              niibotAuth={niibotAuth}
              twitchRewards={twitchRewards}
              onRewardSelect={handleRewardSelect}
              onAuthToggle={handleAuthToggle}
            />
          </SlideUp>
          <SlideUp delay={0.15}>
            <ActivationCodes />
          </SlideUp>
        </div>
      </div>
    </PageMain>
  )
}
