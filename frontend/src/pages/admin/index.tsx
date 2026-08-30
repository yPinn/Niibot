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

export default function AdminPage() {
  useDocumentTitle('Admin')

  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)
  const [channelFilter, setChannelFilter] = useState<
    'all' | 'issues' | 'suspended' | 'healthy' | 'paused' | 'pending'
  >('all')

  const { healthyChannels, issueChannels, pausedChannels, pendingChannels, suspendedChannels } =
    useMemo(() => {
      const sortByLive = (chs: AdminChannel[]) =>
        [...chs].sort((a, b) => (b.is_live ? 1 : 0) - (a.is_live ? 1 : 0))
      const nonBots = channels.filter(ch => !ch.is_bot)
      // Pending/suspended owners are always disabled (084's trigger), so they
      // must be bucketed by membership_status before the is_enabled split —
      // otherwise they'd be indistinguishable from an active owner who
      // manually paused the bot.
      const activeMembers = nonBots.filter(ch => ch.membership_status === 'active')
      const active = activeMembers.filter(ch => ch.is_enabled)
      const paused = activeMembers.filter(ch => !ch.is_enabled)
      return {
        healthyChannels: sortByLive(
          active.filter(ch => ch.mod_status === 'mod' && ch.missing_scopes.length === 0)
        ),
        issueChannels: sortByLive(
          active.filter(ch => ch.mod_status !== 'mod' || ch.missing_scopes.length > 0)
        ),
        pausedChannels: sortByLive(paused),
        pendingChannels: sortByLive(nonBots.filter(ch => ch.membership_status === 'pending')),
        suspendedChannels: sortByLive(nonBots.filter(ch => ch.membership_status === 'suspended')),
      }
    }, [channels])

  const channelFilters = [
    {
      value: 'all' as const,
      label: '全部',
      channels: [
        ...issueChannels,
        ...pendingChannels,
        ...suspendedChannels,
        ...pausedChannels,
        ...healthyChannels,
      ],
    },
    { value: 'issues' as const, label: '需處理', channels: issueChannels },
    { value: 'pending' as const, label: '待審核', channels: pendingChannels },
    { value: 'suspended' as const, label: '已停權', channels: suspendedChannels },
    { value: 'paused' as const, label: '監控暫停', channels: pausedChannels },
    { value: 'healthy' as const, label: '正常', channels: healthyChannels },
  ]
  const allUserChannels = channelFilters[0].channels
  const visibleChannels =
    channelFilters.find(filter => filter.value === channelFilter)?.channels ?? []

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

  const handleRewardSelect = async (rewardTitle: string) => {
    if (!niibotAuth) return
    try {
      const updated = await updateRedemptionConfig('niibot_auth', {
        reward_name: rewardTitle === '__none__' ? '' : rewardTitle,
        enabled: niibotAuth.enabled,
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
                <CardTitle className="text-card-title">使用者與頻道</CardTitle>
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
                        <span className="font-mono text-label opacity-75">
                          {filter.channels.length}
                        </span>
                      </Button>
                    ))}
                  </div>

                  <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-3">
                    {visibleChannels.map(ch => (
                      <ChannelCard
                        key={ch.id}
                        ch={ch}
                        onSuspend={ch.membership_status === 'active' ? handleSuspend : undefined}
                        onReinstate={
                          ch.membership_status === 'suspended' ? handleReinstate : undefined
                        }
                      />
                    ))}
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
