import { useState } from 'react'
import { toast } from 'sonner'

import type { BotTokenInfo } from '@/api/admin'
import { type BotInviteCreated, createSystemBotResetInvite } from '@/api/botAccounts'
import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { Icon, Spinner, TwitchRoleBadge } from '@/components/primitives'
import {
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
  Switch,
} from '@/components/ui'

import { ScopeSection } from './ScopeSection'

const BOT_STATUS_CONFIG = {
  ok: {
    label: 'All scopes granted',
    icon: 'fa-solid fa-shield-check',
    textClass: 'text-status-online',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  missing: {
    label: 'scopes missing',
    icon: 'fa-solid fa-lock',
    textClass: 'text-status-info',
    className: 'border-status-info/20 bg-status-info/10 text-status-info',
  },
  no_token: {
    label: 'No bot token',
    icon: 'fa-solid fa-rotate-exclamation',
    textClass: 'text-status-warning',
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
  const [resetting, setResetting] = useState(false)
  const [resetInvite, setResetInvite] = useState<BotInviteCreated | null>(null)

  const createResetInvite = async () => {
    setResetting(true)
    try {
      setResetInvite(await createSystemBotResetInvite())
    } catch {
      toast.error('建立 Niibot reset 邀請失敗')
    } finally {
      setResetting(false)
    }
  }

  return (
    <Card className="lg:h-full">
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-solid fa-robot" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">Bot 設定</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-section">
        {botLoading ? (
          <>
            <div className="flex items-center gap-element rounded-md border border-border px-2 py-1.5">
              <Skeleton className="size-8 rounded-full shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="size-4.5 rounded shrink-0" />
            </div>
            <Skeleton className="h-40 w-full rounded-md" />
          </>
        ) : bot && botCfg ? (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="flex items-center gap-element w-full rounded-md border border-border px-2 py-1.5 hover:bg-accent transition-colors text-left select-none"
                >
                  {bot.avatar && (
                    <img
                      src={bot.avatar}
                      alt={bot.display_name || bot.name}
                      className="size-8 rounded-full object-cover shrink-0"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <TwitchRoleBadge role="bot" size={18} className="shrink-0 opacity-80" />
                      <p className="text-sub font-medium truncate">
                        {bot.display_name || bot.name}
                      </p>
                    </div>
                    <p className="text-label text-muted-foreground font-mono truncate">
                      {bot.name}
                    </p>
                  </div>
                  <Icon
                    icon="fa-solid fa-chevron-down"
                    size="badge"
                    wrapperClassName="text-muted-foreground/60 shrink-0"
                  />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                style={{ width: 'var(--radix-dropdown-menu-trigger-width)' }}
              >
                <DropdownMenuLabel className="font-normal">
                  <div className="flex items-center gap-element">
                    {bot.avatar && (
                      <img src={bot.avatar} alt="" className="size-6 rounded-full shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sub font-medium truncate">
                        {bot.display_name || bot.name}
                      </p>
                      <p className="text-label text-muted-foreground font-mono truncate">
                        {bot.name}
                      </p>
                    </div>
                    <Icon
                      icon={botCfg.icon}
                      size="badge"
                      className={`shrink-0 ${botCfg.textClass}`}
                    />
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem disabled className="text-muted-foreground/50 gap-element">
                  <Icon icon="fa-solid fa-plus" size="xs" />
                  新增帳號（尚未支援）
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <ScopeSection granted={bot.granted_scopes} missing={bot.missing_scopes} />
            <div className="space-y-2 rounded-md border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-label font-medium">Bot Token</p>
                  <p className="text-label text-muted-foreground">
                    建立限定 {bot.display_name || bot.name} 的一次性授權連結。
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => void createResetInvite()}
                  disabled={resetting}
                >
                  {resetting && <Spinner className="mr-1" />}
                  更新 Niibot Token
                </Button>
              </div>
              {resetInvite && (
                <div className="flex flex-col gap-2 sm:flex-row">
                  <Input value={resetInvite.public_url} readOnly aria-label="Niibot reset URL" />
                  <Button size="sm" variant="outline" asChild>
                    <a href={resetInvite.public_url} target="_blank" rel="noopener noreferrer">
                      開啟
                    </a>
                  </Button>
                </div>
              )}
            </div>
          </>
        ) : null}

        <Separator />

        <div className="space-y-element">
          <div className="flex items-center gap-element">
            <Icon icon="fa-solid fa-coins" size="xs" wrapperClassName="text-muted-foreground" />
            <p className="text-label font-medium text-muted-foreground select-none">授權兌換</p>
          </div>
          {redemptionLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : !niibotAuth ? (
            <p className="text-label text-muted-foreground">找不到 niibot_auth 兌換設定。</p>
          ) : (
            <div className="flex items-center justify-between gap-element">
              {rewardsLoading ? (
                <Skeleton className="h-9 flex-1" />
              ) : twitchRewards.length === 0 ? (
                <span className="text-label text-muted-foreground">請先在 Twitch 建立自訂獎勵</span>
              ) : (
                <Select
                  value={
                    niibotAuth.reward_id ??
                    twitchRewards.find(reward => reward.title === niibotAuth.reward_name)?.id ??
                    '__none__'
                  }
                  onValueChange={onRewardSelect}
                >
                  <SelectTrigger size="sm" className="flex-1 min-w-0">
                    <SelectValue placeholder="選擇獎勵..." />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__" className="text-muted-foreground">
                      未選擇
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
                aria-label="啟用 Niibot 認證"
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
