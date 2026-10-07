import { useState } from 'react'
import { toast } from 'sonner'

import type { BotTokenInfo } from '@/api/admin'
import { type BotInviteCreated, createSystemBotResetInvite } from '@/api/botAccounts'
import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { Icon, Spinner, TwitchRoleBadge } from '@/components/primitives'
import { TwitchAccountIdentity } from '@/components/TwitchAccountIdentity'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
  Switch,
} from '@/components/ui'

const BOT_STATUS_CONFIG = {
  ok: {
    label: '已就緒',
    description: '',
    action: '更新授權',
    icon: 'fa-solid fa-shield-check',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  missing: {
    label: '權限不足',
    description: '部分功能無法使用。',
    action: '補充授權',
    icon: 'fa-solid fa-lock',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
  no_token: {
    label: '尚未授權',
    description: '尚未連結 Bot 帳號。',
    action: '連結帳號',
    icon: 'fa-solid fa-rotate-exclamation',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
}

export function BotStatusPanel({
  bot,
  botLoading,
  redemptionLoading,
  rewardsLoading,
  niibotAuth,
  twitchRewards,
  onRewardSelect,
  onAuthToggle,
}: {
  bot: BotTokenInfo | null
  botLoading: boolean
  redemptionLoading: boolean
  rewardsLoading: boolean
  niibotAuth: RedemptionConfig | null
  twitchRewards: TwitchReward[]
  onRewardSelect: (value: string) => void
  onAuthToggle: () => void
}) {
  const botCfg = bot ? BOT_STATUS_CONFIG[bot.status] : null
  const botName = bot ? bot.display_name || bot.name : ''
  const [resetting, setResetting] = useState(false)
  const [resetInvite, setResetInvite] = useState<BotInviteCreated | null>(null)

  const createResetInvite = async () => {
    setResetting(true)
    try {
      setResetInvite(await createSystemBotResetInvite())
    } catch {
      toast.error('建立 Bot 授權連結失敗')
    } finally {
      setResetting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-solid fa-robot" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">Bot 設定</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-section">
        {botLoading ? (
          <div className="space-y-section">
            <div className="flex items-center gap-element">
              <Skeleton className="size-10 shrink-0 rounded-full" />
              <div className="flex-1 space-y-element">
                <Skeleton className="h-4 w-28" />
                <Skeleton className="h-3 w-20" />
              </div>
              <Skeleton className="h-6 w-16 rounded-full" />
            </div>
            <Skeleton className="h-8 w-full rounded-md" />
          </div>
        ) : bot && botCfg ? (
          <div className="space-y-section">
            <div className="flex items-start gap-element">
              <TwitchAccountIdentity
                className="flex-1"
                avatar={bot.avatar}
                displayName={botName}
                login={bot.name}
                badges={<TwitchRoleBadge role="bot" size={18} className="shrink-0 opacity-80" />}
              />
              <Badge className={`shrink-0 gap-1.5 ${botCfg.className}`}>
                <Icon icon={botCfg.icon} size="xs" />
                {botCfg.label}
              </Badge>
            </div>

            {resetInvite ? (
              <div className="bg-muted flex flex-col gap-element rounded-lg p-section sm:flex-row sm:items-center sm:justify-between">
                <p className="text-label text-muted-foreground">
                  以 {botName} 登入授權（單次有效）
                </p>
                <Button size="sm" asChild>
                  <a
                    href={resetInvite.public_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label="開啟授權頁"
                  >
                    開啟授權頁
                    <Icon icon="fa-solid fa-arrow-up-right-from-square" size="xs" />
                  </a>
                </Button>
              </div>
            ) : (
              <div className="flex flex-col gap-element sm:flex-row sm:items-center sm:justify-between">
                {botCfg.description && (
                  <p className="text-label text-muted-foreground">{botCfg.description}</p>
                )}
                <Button
                  size="sm"
                  // Routine refresh when healthy; the page's primary action when not.
                  variant={bot.status === 'ok' ? 'ghost' : 'default'}
                  className="shrink-0 sm:ml-auto"
                  onClick={() => void createResetInvite()}
                  disabled={resetting}
                >
                  {resetting && <Spinner className="mr-1" />}
                  {botCfg.action}
                </Button>
              </div>
            )}
          </div>
        ) : (
          <p className="text-sub text-muted-foreground">無法載入 Bot 狀態</p>
        )}

        <Separator />

        <div className="space-y-element">
          <div className="flex items-center gap-element">
            <Icon icon="fa-solid fa-coins" size="xs" wrapperClassName="text-muted-foreground" />
            <p className="select-none text-label font-medium">使用資格獎勵</p>
          </div>
          {redemptionLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : !niibotAuth ? (
            <p className="text-label text-muted-foreground">無法載入</p>
          ) : (
            <div className="flex items-center justify-between gap-element">
              {rewardsLoading ? (
                <Skeleton className="h-9 flex-1" />
              ) : twitchRewards.length === 0 ? (
                <span className="text-label text-muted-foreground">尚無 Twitch 自訂獎勵</span>
              ) : (
                <Select
                  value={
                    niibotAuth.reward_id ??
                    twitchRewards.find(reward => reward.title === niibotAuth.reward_name)?.id ??
                    '__none__'
                  }
                  onValueChange={onRewardSelect}
                >
                  <SelectTrigger size="sm" className="min-w-0 flex-1" aria-label="使用資格獎勵">
                    <SelectValue placeholder="選擇 Twitch 獎勵" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" className="text-muted-foreground">
                      不綁定獎勵
                    </SelectItem>
                    {twitchRewards.map(reward => (
                      <SelectItem key={reward.id} value={reward.id}>
                        {reward.title} ({reward.cost.toLocaleString()} 點)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <Switch
                aria-label="啟用使用資格兌換"
                checked={niibotAuth.enabled}
                onCheckedChange={onAuthToggle}
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}
