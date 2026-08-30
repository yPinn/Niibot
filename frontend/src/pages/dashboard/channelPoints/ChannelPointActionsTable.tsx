import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { SortableHead } from '@/components/SortableHead'
import { TableEmptyRow } from '@/components/TableEmptyRow'
import { TableShell } from '@/components/TableShell'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Switch,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui'
import type { SortState } from '@/hooks/useSortState'

import { ACTION_TYPE_DESCRIPTIONS, ACTION_TYPE_LABELS } from './constants'

export type ChannelPointSortKey = 'action_type' | 'reward_name' | 'enabled'

interface ChannelPointActionsTableProps {
  redemptions: RedemptionConfig[]
  twitchRewards: TwitchReward[]
  redemptionLoading: boolean
  rewardsLoading: boolean
  sort: SortState<ChannelPointSortKey>
  isAffiliate: boolean
  onToggle: (redemption: RedemptionConfig) => void
  onRewardSelect: (redemption: RedemptionConfig, rewardId: string) => void
  onEditCheckinSettings: () => void
}

export function ChannelPointActionsTable({
  redemptions,
  twitchRewards,
  redemptionLoading,
  rewardsLoading,
  sort,
  isAffiliate,
  onToggle,
  onRewardSelect,
  onEditCheckinSettings,
}: ChannelPointActionsTableProps) {
  return (
    <Card className="relative w-full max-w-7xl overflow-hidden">
      {!isAffiliate && (
        <AffiliateLockOverlay
          message="取得 Twitch 實況盟友或合作夥伴資格後即可設定頻道點數動作"
          className="rounded-[inherit]"
        />
      )}
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2">
          頻道點數動作
          <Badge variant="secondary">Twitch 管理獎勵</Badge>
        </CardTitle>
        <CardDescription>
          將既有 Twitch 自訂獎勵綁定至 Niibot 功能；成本與兌換限制仍由 Twitch 管理。
        </CardDescription>
      </CardHeader>
      <CardContent>
        {redemptionLoading ? (
          <TableSkeletonRows count={5} />
        ) : (
          <TableShell>
            <TableHeader>
              <TableRow>
                <SortableHead className="w-[32%]" sortKey="action_type" sort={sort}>
                  動作
                </SortableHead>
                <SortableHead sortKey="reward_name" sort={sort}>
                  Twitch 獎勵
                </SortableHead>
                <SortableHead className="w-24 text-center" sortKey="enabled" sort={sort}>
                  狀態
                </SortableHead>
                <TableHead className="w-24 text-right">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {redemptions.length === 0 ? (
                <TableEmptyRow
                  colSpan={4}
                  icon="fa-solid fa-coins"
                  title="尚無頻道點數動作"
                  description="重新載入頁面；若問題持續發生，請檢查頻道連線狀態。"
                />
              ) : (
                redemptions.map(redemption => {
                  const actionLabel =
                    ACTION_TYPE_LABELS[redemption.action_type] ?? redemption.action_type
                  return (
                    <TableRow key={redemption.action_type}>
                      <TableCell>
                        <p className="font-medium">{actionLabel}</p>
                        <p className="mt-0.5 text-label text-muted-foreground">
                          {ACTION_TYPE_DESCRIPTIONS[redemption.action_type]}
                        </p>
                      </TableCell>
                      <TableCell>
                        {rewardsLoading ? (
                          <Skeleton className="h-8 w-full max-w-sm" />
                        ) : twitchRewards.length === 0 ? (
                          <span className="text-sub text-muted-foreground">
                            請先在 Twitch 建立自訂獎勵
                          </span>
                        ) : (
                          <Select
                            value={
                              redemption.reward_id ??
                              twitchRewards.find(reward => reward.title === redemption.reward_name)
                                ?.id ??
                              '__none__'
                            }
                            onValueChange={rewardId => onRewardSelect(redemption, rewardId)}
                          >
                            <SelectTrigger
                              aria-label={`${actionLabel}的 Twitch 獎勵`}
                              size="sm"
                              className="w-full max-w-sm"
                            >
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
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          aria-label={`啟用 ${actionLabel}`}
                          checked={redemption.enabled}
                          disabled={!redemption.reward_id}
                          onCheckedChange={() => onToggle(redemption)}
                        />
                      </TableCell>
                      <TableCell className="text-right">
                        {redemption.action_type === 'checkin' && (
                          <Button
                            variant="ghost"
                            size="sm"
                            aria-label={`編輯${actionLabel}設定`}
                            onClick={onEditCheckinSettings}
                          >
                            設定
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })
              )}
            </TableBody>
          </TableShell>
        )}
      </CardContent>
    </Card>
  )
}
