import type { ReactNode } from 'react'

import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { Icon } from '@/components/primitives'
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
  Skeleton,
} from '@/components/ui'

interface CheckinTriggerCardProps {
  config: RedemptionConfig | null
  rewards: TwitchReward[]
  loading: boolean
  loadFailed: boolean
  isAffiliate: boolean
  onRetry: () => void
}

function getBoundReward(config: RedemptionConfig | null, rewards: TwitchReward[]) {
  if (!config) return undefined
  if (config.reward_id) return rewards.find(reward => reward.id === config.reward_id)
  return rewards.find(reward => reward.title === config.reward_name)
}

function LimitBadge({ children }: { children: ReactNode }) {
  return <Badge variant="outline">{children}</Badge>
}

export function CheckinTriggerCard({
  config,
  rewards,
  loading,
  loadFailed,
  isAffiliate,
  onRetry,
}: CheckinTriggerCardProps) {
  const boundReward = getBoundReward(config, rewards)
  const bindingLabel = boundReward?.title ?? config?.reward_name
  const statusLabel = !bindingLabel ? '未綁定' : config?.enabled ? '已啟用' : '已停用'

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          Twitch 點數簽到
          <Badge variant="secondary">唯讀監聽</Badge>
        </CardTitle>
        <CardDescription>
          觀眾兌換指定獎勵時執行每日簽到；同一天重複兌換不會增加簽到次數。
        </CardDescription>
        <CardAction>
          <Badge variant={config?.enabled && bindingLabel ? 'default' : 'outline'}>
            {statusLabel}
          </Badge>
        </CardAction>
      </CardHeader>

      <CardContent className="grid gap-section xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.8fr)]">
        {loading ? (
          <div className="space-y-3 xl:col-span-2">
            <Skeleton className="h-9 w-full max-w-md" />
            <Skeleton className="h-20 w-full" />
          </div>
        ) : loadFailed ? (
          <Alert variant="destructive" className="xl:col-span-2">
            <Icon icon="fa-solid fa-circle-exclamation" />
            <AlertTitle>無法載入 Twitch 簽到設定</AlertTitle>
            <AlertDescription>
              <Button size="sm" variant="outline" onClick={onRetry}>
                重新載入
              </Button>
            </AlertDescription>
          </Alert>
        ) : !isAffiliate ? (
          <Alert className="xl:col-span-2">
            <Icon icon="fa-brands fa-twitch" />
            <AlertTitle>頻道點數尚不可用</AlertTitle>
            <AlertDescription>
              Twitch 頻道點數僅開放給實況盟友與合作夥伴；仍可繼續使用聊天指令簽到。
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <div className="flex min-w-0 flex-col gap-3">
              <div className="space-y-1.5">
                <p className="text-label font-medium text-muted-foreground">Twitch 自訂獎勵</p>
                <p className="text-content font-semibold">
                  {bindingLabel ?? '尚未綁定簽到獎勵'}
                  {boundReward && (
                    <span className="font-normal text-muted-foreground">
                      {' '}
                      · {boundReward.cost.toLocaleString()} 點
                    </span>
                  )}
                </p>
                <p className="text-label text-muted-foreground">
                  此處僅顯示目前綁定；獎勵與啟用狀態統一在 Channel Points 管理。
                </p>
              </div>

              {boundReward && (
                <div className="flex flex-wrap gap-2" aria-label="Twitch 獎勵限制摘要">
                  <LimitBadge>{boundReward.cost.toLocaleString()} 點</LimitBadge>
                  <LimitBadge>
                    每人每場 {boundReward.max_per_user_per_stream ?? '不限'} 次
                  </LimitBadge>
                  <LimitBadge>單場總量 {boundReward.max_per_stream ?? '不限'} 次</LimitBadge>
                  <LimitBadge>
                    {boundReward.should_redemptions_skip_request_queue
                      ? '自動完成兌換'
                      : '進入待處理佇列'}
                  </LimitBadge>
                </div>
              )}

              {boundReward && boundReward.cost !== 10 && (
                <p className="text-label text-status-warning">
                  請回 Twitch 調整為建議的 10 點；Niibot 不會代為修改獎勵成本。
                </p>
              )}
              {boundReward && boundReward.max_per_user_per_stream !== 1 && (
                <p className="text-label text-status-warning">
                  建議在 Twitch 設定每位使用者每場最多 1 次，減少無法退款的重複兌換。
                </p>
              )}
              {boundReward && !boundReward.should_redemptions_skip_request_queue && (
                <p className="text-label text-status-warning">
                  建議在 Twitch 開啟略過獎勵請求佇列，避免簽到後仍顯示待處理。
                </p>
              )}
              {boundReward &&
                (!boundReward.is_enabled || boundReward.is_paused || !boundReward.is_in_stock) && (
                  <p className="text-label text-status-warning">
                    目前獎勵不可兌換，請回 Twitch 檢查啟用、暫停與庫存設定。
                  </p>
                )}
            </div>

            <div className="flex flex-col justify-between gap-3 rounded-lg border bg-muted/40 p-section">
              <div className="space-y-2">
                <p className="text-content font-semibold">Twitch 保有設定控制權</p>
                <p className="text-sub text-muted-foreground">
                  Niibot 不會建立、修改或退款 Twitch 獎勵，只會讀取獎勵資料並監聽兌換事件。
                  若觀眾同一天重複兌換，簽到次數不會增加，但點數也無法由 Niibot 退回。
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Button asChild className="self-start">
                  <a href="/channel-points">前往 Channel Points</a>
                </Button>
                <Button asChild variant="outline" className="self-start">
                  <a href="https://dashboard.twitch.tv/" target="_blank" rel="noreferrer">
                    前往 Twitch 設定
                    <Icon icon="fa-solid fa-arrow-up-right-from-square" className="ml-1.5" />
                  </a>
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
