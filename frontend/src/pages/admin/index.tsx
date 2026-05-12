import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { type AdminChannel, getAdminChannels, type ModStatus } from '@/api/admin'
import {
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  type TwitchReward,
  updateRedemptionConfig,
} from '@/api/events'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  SlideUp,
  Switch,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ── Channels panel ────────────────────────────────────────────────────────────

const MOD_STATUS_CONFIG: Record<ModStatus, { label: string; icon: string; className: string }> = {
  mod: {
    label: 'mod',
    icon: 'fa-solid fa-shield-check',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  no_mod: {
    label: 'no mod',
    icon: 'fa-solid fa-shield-xmark',
    className: 'border-status-offline/20 bg-status-offline/10 text-status-offline',
  },
  token_error: {
    label: 'token expired',
    icon: 'fa-solid fa-rotate-exclamation',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
  scope_error: {
    label: 'scope outdated',
    icon: 'fa-solid fa-lock',
    className: 'border-status-info/20 bg-status-info/10 text-status-info',
  },
}

function ModStatusBadge({ status }: { status: ModStatus }) {
  const cfg = MOD_STATUS_CONFIG[status] ?? MOD_STATUS_CONFIG.token_error
  return (
    <Badge className={`gap-1 text-label ${cfg.className}`}>
      <Icon icon={cfg.icon} size="xs" />
      {cfg.label}
    </Badge>
  )
}

function ChannelCard({ ch }: { ch: AdminChannel }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-border bg-card p-3 text-center">
      <div className="relative">
        <img src={ch.avatar} alt={ch.display_name} className="size-10 rounded-full object-cover" />
        {ch.is_live && (
          <span className="absolute -bottom-0.5 -right-0.5 size-3 rounded-full border-2 border-card bg-status-live" />
        )}
      </div>
      <div className="w-full min-w-0">
        <p className="text-sub font-medium truncate">{ch.display_name}</p>
        <p className="text-label text-muted-foreground font-mono truncate">{ch.name}</p>
      </div>
      <ModStatusBadge status={ch.mod_status} />
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  useDocumentTitle('Admin')

  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)

  const [niibotAuth, setNiibotAuth] = useState<RedemptionConfig | null>(null)
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)

  useEffect(() => {
    getAdminChannels()
      .then(setChannels)
      .catch(() => setChannels([]))
      .finally(() => setChannelsLoading(false))

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

      {/* Niibot auth redemption */}
      <SlideUp>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Icon icon="fa-solid fa-coins" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">Niibot 授權兌換</CardTitle>
            </div>
            <CardDescription>指定觀眾兌換後取得 Niibot 啟用碼的頻道點數獎勵</CardDescription>
          </CardHeader>
          <CardContent>
            {redemptionLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : !niibotAuth ? (
              <p className="text-sub text-muted-foreground py-2">找不到 niibot_auth 兌換設定。</p>
            ) : (
              <div className="flex flex-wrap items-center gap-4">
                {rewardsLoading ? (
                  <Skeleton className="h-9 w-52" />
                ) : twitchRewards.length === 0 ? (
                  <span className="text-sub text-muted-foreground">請先在 Twitch 建立自訂獎勵</span>
                ) : (
                  <Select
                    value={niibotAuth.reward_name || '__none__'}
                    onValueChange={handleRewardSelect}
                  >
                    <SelectTrigger size="sm" className="w-52">
                      <SelectValue placeholder="選擇獎勵..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__" className="text-muted-foreground">
                        未選擇
                      </SelectItem>
                      {twitchRewards.map(reward => (
                        <SelectItem key={reward.id} value={reward.title}>
                          {reward.title} ({reward.cost.toLocaleString()} 點)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <div className="flex items-center gap-2 ml-auto">
                  <span className="text-sub text-muted-foreground">啟用</span>
                  <Switch checked={niibotAuth.enabled} onCheckedChange={handleAuthToggle} />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      {/* Channels */}
      <SlideUp>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Icon icon="fa-brands fa-twitch" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">Monitored Channels</CardTitle>
            </div>
            <CardAction>
              <Badge variant="outline" className="font-mono text-label">
                {channelsLoading ? '…' : channels.length}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            {channelsLoading ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                  <Skeleton key={i} className="h-28 w-full rounded-lg" />
                ))}
              </div>
            ) : channels.length === 0 ? (
              <p className="text-sub text-muted-foreground py-2">No monitored channels.</p>
            ) : (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
                {channels.map(ch => (
                  <ChannelCard key={ch.id} ch={ch} />
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </SlideUp>
    </PageMain>
  )
}
