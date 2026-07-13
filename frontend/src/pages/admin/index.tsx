import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type AdminChannel,
  type BotTokenInfo,
  getAdminBotStatus,
  getAdminChannels,
  reinstateMembership,
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
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Skeleton,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import { ActivationCard } from './components/ActivationCard'
import { BotStatusPanel } from './components/BotStatusPanel'
import { ChannelCard } from './components/ChannelCard'

export default function AdminPage() {
  useDocumentTitle('Admin')

  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)

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
    } catch {
      toast.error('更新失敗')
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
    } catch {
      toast.error('恢復失敗')
    }
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
    } catch {
      setNiibotAuth(prev => (prev ? { ...prev, enabled: !newEnabled } : prev))
      toast.error('切換狀態失敗')
    }
  }

  return (
    <PageMain className="lg:gap-card">
      <PageHeader title="Admin" description="管理頻道點數兌換與監控頻道。" />

      <div className="grid grid-cols-1 gap-card items-start lg:grid-cols-[1fr_360px]">
        <SlideUp>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-element">
                <Icon
                  icon="fa-brands fa-twitch"
                  size="sm"
                  wrapperClassName="text-muted-foreground"
                />
                <CardTitle className="text-card-title">監控頻道</CardTitle>
              </div>
              <CardAction>
                <Badge variant="outline" className="font-mono text-label">
                  {channelsLoading ? '…' : channels.length}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              {channelsLoading ? (
                <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="w-full aspect-video rounded-lg" />
                  ))}
                </div>
              ) : channels.length === 0 ? (
                <p className="text-sub text-muted-foreground py-2">No monitored channels.</p>
              ) : (
                <div className="space-y-section">
                  {issueChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-status-warning select-none">
                          需注意
                        </span>
                        <Badge className="border-status-warning/20 bg-status-warning/10 text-status-warning font-mono text-label">
                          {issueChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {issueChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} />
                        ))}
                      </div>
                    </div>
                  )}

                  {suspendedChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-destructive select-none">
                          暫停授權
                        </span>
                        <Badge className="border-destructive/20 bg-destructive/10 text-destructive font-mono text-label">
                          {suspendedChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {suspendedChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} onReinstate={handleReinstate} />
                        ))}
                      </div>
                    </div>
                  )}

                  <div>
                    {issueChannels.length > 0 && (
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                          正常
                        </span>
                        <Badge variant="outline" className="font-mono text-label">
                          {healthyChannels.length}
                        </Badge>
                      </div>
                    )}
                    <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                      {healthyChannels.map(ch => (
                        <ChannelCard key={ch.id} ch={ch} />
                      ))}
                    </div>
                  </div>

                  {pausedChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                          暫停中
                        </span>
                        <Badge variant="outline" className="font-mono text-label">
                          {pausedChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {pausedChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} />
                        ))}
                      </div>
                    </div>
                  )}

                  {pendingChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                          待審
                        </span>
                        <Badge variant="outline" className="font-mono text-label">
                          {pendingChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {pendingChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </SlideUp>

        <SlideUp delay={0.1}>
          <div className="space-y-card">
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
            <ActivationCard />
          </div>
        </SlideUp>
      </div>
    </PageMain>
  )
}
