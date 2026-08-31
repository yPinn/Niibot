import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type AdminChannel,
  type BotTokenInfo,
  getAdminBotStatus,
  getAdminChannels,
  reinstateMembership,
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
import { Icon, SlideUp } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { toastApiError } from '@/lib/toast-error'

import { ActivationCard } from './components/ActivationCard'
import { BotStatusPanel } from './components/BotStatusPanel'
import { ChannelCard } from './components/ChannelCard'

type ChannelCategoryValue = 'healthy' | 'issues' | 'pending' | 'paused' | 'suspended'
type ChannelFilterValue = 'all' | ChannelCategoryValue

interface ChannelCategoryDefinition {
  value: ChannelCategoryValue
  label: string
  description: string
  icon: string
  toneClassName: string
}

const CHANNEL_CATEGORY_DEFINITIONS: ChannelCategoryDefinition[] = [
  {
    value: 'healthy',
    label: '正常監聽',
    description: '授權與 Bot 狀態正常',
    icon: 'fa-solid fa-shield-check',
    toneClassName: 'text-status-online',
  },
  {
    value: 'issues',
    label: '需處理',
    description: '缺少授權、Token 或 Mod 狀態異常',
    icon: 'fa-solid fa-triangle-exclamation',
    toneClassName: 'text-status-warning',
  },
  {
    value: 'pending',
    label: '待審核',
    description: '等待管理員確認使用資格',
    icon: 'fa-solid fa-hourglass-half',
    toneClassName: 'text-status-info',
  },
  {
    value: 'paused',
    label: '監控暫停',
    description: '授權有效，但 Bot 目前未監控',
    icon: 'fa-solid fa-circle-pause',
    toneClassName: 'text-muted-foreground',
  },
  {
    value: 'suspended',
    label: '已停權',
    description: '使用權限與 Bot 監控皆已停止',
    icon: 'fa-solid fa-ban',
    toneClassName: 'text-destructive',
  },
]

function getChannelCategory(ch: AdminChannel): ChannelCategoryValue {
  if (ch.membership_status === 'pending') return 'pending'
  if (ch.membership_status === 'suspended') return 'suspended'
  if (!ch.is_enabled) return 'paused'
  if (ch.mod_status !== 'mod' || ch.missing_scopes.length > 0) return 'issues'
  return 'healthy'
}

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
  const visibleCategories =
    channelFilter === 'all'
      ? channelCategories.filter(category => category.channels.length > 0)
      : channelCategories.filter(category => category.value === channelFilter)
  const channelFilters = [
    { value: 'all' as const, label: '全部', count: allUserChannels.length },
    ...channelCategories.map(category => ({
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

  const handleReinstate = async (ch: AdminChannel) => {
    if (!ch.owner_user_id) return
    try {
      await reinstateMembership(ch.owner_user_id, 'admin_reinstate')
      toast.success(`${ch.display_name} 授權已恢復`)
      // Refetch rather than patch locally: reinstating flips channels.enabled
      // server-side (084's trigger) and re-derives mod_status, neither of
      // which the client can compute from the stale suspended-state record.
      setChannels(await getAdminChannels())
    } catch (e) {
      toastApiError(e, '恢復失敗')
    }
  }

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
    void getAdminChannels()
      .then(setChannels)
      .catch(() => undefined)
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
              <CardAction>
                <Badge variant="outline" className="font-mono text-label">
                  {channelsLoading ? '…' : allUserChannels.length}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              {channelsLoading ? (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-video w-full rounded-lg" />
                  ))}
                </div>
              ) : allUserChannels.length === 0 ? (
                <div className="rounded-lg border border-dashed px-4 py-6 text-center">
                  <p className="text-sub font-medium">目前沒有可管理的使用者頻道</p>
                  <p className="text-label text-muted-foreground">
                    完成授權後，使用者會顯示在這裡。
                  </p>
                </div>
              ) : (
                <div className="space-y-section">
                  <div
                    className="flex flex-wrap items-center gap-element"
                    role="group"
                    aria-label="使用者狀態篩選"
                  >
                    {channelFilters.map(filter => (
                      <Button
                        key={filter.value}
                        type="button"
                        size="sm"
                        variant={channelFilter === filter.value ? 'default' : 'outline'}
                        onClick={() => setChannelFilter(filter.value)}
                        aria-pressed={channelFilter === filter.value}
                      >
                        {filter.label}
                        <span className="font-mono text-label opacity-75">{filter.count}</span>
                      </Button>
                    ))}
                  </div>

                  <div className="space-y-card">
                    {visibleCategories.map(category => {
                      const headingId = `channel-category-${category.value}`
                      return (
                        <section
                          key={category.value}
                          aria-labelledby={headingId}
                          className="space-y-section"
                        >
                          <div className="flex items-start justify-between gap-section border-b pb-element">
                            <div className="flex min-w-0 items-start gap-element">
                              <Icon
                                icon={category.icon}
                                size="xs"
                                wrapperClassName={`mt-0.5 ${category.toneClassName}`}
                              />
                              <div className="min-w-0">
                                <h3 id={headingId} className="text-sub font-semibold">
                                  {category.label}
                                </h3>
                                <p className="text-label text-muted-foreground">
                                  {category.description}
                                </p>
                              </div>
                            </div>
                            <Badge
                              variant="outline"
                              className={`font-mono text-label ${category.toneClassName}`}
                            >
                              {category.channels.length}
                            </Badge>
                          </div>

                          {category.channels.length === 0 ? (
                            <div className="rounded-lg border border-dashed px-4 py-6 text-center">
                              <p className="text-sub font-medium">目前沒有{category.label}的頻道</p>
                            </div>
                          ) : (
                            <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                              {category.channels.map(ch => (
                                <ChannelCard
                                  key={ch.id}
                                  ch={ch}
                                  onSuspend={
                                    ch.membership_status === 'active' ? handleSuspend : undefined
                                  }
                                  onReinstate={
                                    ch.membership_status === 'suspended'
                                      ? handleReinstate
                                      : undefined
                                  }
                                />
                              ))}
                            </div>
                          )}
                        </section>
                      )
                    })}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </SlideUp>

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

        <SlideUp delay={0.15} className="lg:col-span-2" role="region" aria-label="授權管理">
          <ActivationCard />
        </SlideUp>
      </div>
    </PageMain>
  )
}
