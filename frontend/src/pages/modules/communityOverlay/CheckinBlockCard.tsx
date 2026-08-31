import type { ReactNode } from 'react'

import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Skeleton,
} from '@/components/ui'

interface CheckinBlockCardProps {
  config: RedemptionConfig | null
  rewards: TwitchReward[]
  loading: boolean
  loadFailed: boolean
  isAffiliate: boolean
  testing: boolean
  open: boolean
  themeStatus: string
  themeChanged: boolean
  onOpenChange: (open: boolean) => void
  onRetry: () => void
  onTest: () => void
  children: ReactNode
}

function getBoundReward(config: RedemptionConfig | null, rewards: TwitchReward[]) {
  if (!config) return undefined
  if (config.reward_id) return rewards.find(reward => reward.id === config.reward_id)
  return rewards.find(reward => reward.title === config.reward_name)
}

export function CheckinBlockCard({
  config,
  rewards,
  loading,
  loadFailed,
  isAffiliate,
  testing,
  open,
  themeStatus,
  themeChanged,
  onOpenChange,
  onRetry,
  onTest,
  children,
}: CheckinBlockCardProps) {
  const boundReward = getBoundReward(config, rewards)
  const bindingLabel = boundReward?.title ?? config?.reward_name
  const statusLabel = !bindingLabel ? '未綁定' : config?.enabled ? '已啟用' : '已停用'

  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <Card className="min-w-0">
        <CardHeader className="has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[1fr_auto]">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <h3>每日簽到</h3>
            <Badge variant="secondary">集點卡</Badge>
            <Badge variant={themeChanged ? 'secondary' : 'outline'}>{themeStatus}</Badge>
          </CardTitle>
          <CardDescription>觀眾完成簽到時，在直播畫面顯示累積天數。</CardDescription>
          <CardAction className="col-start-1 row-span-1 row-start-3 flex flex-wrap items-center justify-start gap-2 justify-self-stretch sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:justify-end sm:justify-self-end">
            <Button
              size="sm"
              variant="outline"
              aria-label="測試每日簽到動畫"
              disabled={testing}
              onClick={onTest}
            >
              {testing ? (
                <Spinner className="mr-1.5" />
              ) : (
                <Icon icon="fa-solid fa-play" className="mr-1.5 text-label" />
              )}
              測試動畫
            </Button>
            <CollapsibleTrigger asChild>
              <Button
                size="sm"
                variant="ghost"
                aria-label={open ? '收合每日簽到設定' : '展開每日簽到設定'}
              >
                <Icon
                  icon="fa-solid fa-chevron-down"
                  className={`text-label transition-transform ${open ? 'rotate-180' : ''}`}
                />
                {open ? '收合設定' : '外觀設定'}
              </Button>
            </CollapsibleTrigger>
          </CardAction>
        </CardHeader>

        <CardContent>
          {loading ? (
            <div className="space-y-3">
              <Skeleton className="h-9 w-full max-w-md" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : loadFailed ? (
            <Alert variant="destructive">
              <Icon icon="fa-solid fa-circle-exclamation" />
              <AlertTitle>無法載入 Twitch 簽到設定</AlertTitle>
              <AlertDescription>
                <Button size="sm" variant="outline" onClick={onRetry}>
                  重新載入
                </Button>
              </AlertDescription>
            </Alert>
          ) : !isAffiliate ? (
            <Alert>
              <Icon icon="fa-brands fa-twitch" />
              <AlertTitle>頻道點數尚不可用</AlertTitle>
              <AlertDescription>
                Twitch 頻道點數僅開放給實況盟友與合作夥伴；仍可繼續使用聊天指令簽到。
              </AlertDescription>
            </Alert>
          ) : (
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div className="grid min-w-0 gap-3 sm:grid-cols-2">
                <div className="space-y-1">
                  <p className="text-label text-muted-foreground">聊天指令</p>
                  <p className="text-content font-semibold">!簽到</p>
                  <p className="text-label text-muted-foreground">每天每人記錄一次</p>
                </div>
                <div className="space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-label text-muted-foreground">頻道點數</p>
                    <Badge variant={config?.enabled && bindingLabel ? 'default' : 'outline'}>
                      {statusLabel}
                    </Badge>
                  </div>
                  <p className="text-content font-semibold">
                    {bindingLabel ?? '尚未綁定'}
                    {boundReward && (
                      <span className="font-normal text-muted-foreground">
                        {' '}
                        · {boundReward.cost.toLocaleString()} 點
                      </span>
                    )}
                  </p>
                  <p className="text-label text-muted-foreground">由 Twitch 管理獎勵</p>
                </div>
              </div>
              <Button asChild size="sm" variant="outline" className="self-start sm:self-auto">
                <a href="/channel-points">管理簽到入口</a>
              </Button>
            </div>
          )}
        </CardContent>

        <CollapsibleContent>
          <div className="mt-section border-t px-card pt-card">{children}</div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
