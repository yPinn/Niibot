import type { RedemptionConfig, TwitchReward } from '@/api/events'
import { AffiliateLockOverlay } from '@/components/AffiliateLockOverlay'
import { SlideUp } from '@/components/primitives'
import { SortableHead } from '@/components/SortableHead'
import { TableEmptyRow } from '@/components/TableEmptyRow'
import { TableShell } from '@/components/TableShell'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
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
  TableHeader,
  TableRow,
} from '@/components/ui'
import type { SortState } from '@/hooks/useSortState'

import { ACTION_TYPE_LABELS } from './constants'
import type { RedemptionSortKey } from './types'

interface RedemptionsCardProps {
  redemptions: RedemptionConfig[]
  twitchRewards: TwitchReward[]
  redemptionLoading: boolean
  rewardsLoading: boolean
  sort: SortState<RedemptionSortKey>
  isAffiliate: boolean
  onToggle: (red: RedemptionConfig) => void
  onRewardSelect: (red: RedemptionConfig, rewardTitle: string) => void
}

export function RedemptionsCard({
  redemptions,
  twitchRewards,
  redemptionLoading,
  rewardsLoading,
  sort,
  isAffiliate,
  onToggle,
  onRewardSelect,
}: RedemptionsCardProps) {
  return (
    <SlideUp inView delay={0.1}>
      <Card className="relative overflow-hidden">
        {!isAffiliate && (
          <AffiliateLockOverlay
            message="取得資格後可設定忠誠點數獎勵"
            className="rounded-[inherit]"
          />
        )}
        <CardHeader>
          <CardTitle>忠誠點數兌換</CardTitle>
          <CardDescription>選擇 Twitch 忠誠點數獎勵對應的動作</CardDescription>
        </CardHeader>
        <CardContent>
          {redemptionLoading ? (
            <TableSkeletonRows />
          ) : (
            <TableShell>
              <TableHeader>
                <TableRow>
                  <SortableHead className="w-[30%]" sortKey="action_type" sort={sort}>
                    動作
                  </SortableHead>
                  <SortableHead sortKey="reward_name" sort={sort}>
                    獎勵名稱
                  </SortableHead>
                  <SortableHead className="w-24 text-center" sortKey="enabled" sort={sort}>
                    狀態
                  </SortableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {redemptions.length === 0 ? (
                  <TableEmptyRow
                    colSpan={3}
                    icon="fa-solid fa-coins"
                    title="尚無兌換設定"
                    description="在 Twitch 上建立頻道點數獎勵後即會顯示於此"
                  />
                ) : (
                  redemptions.map(red => (
                    <TableRow key={red.action_type}>
                      <TableCell className="font-medium">
                        {ACTION_TYPE_LABELS[red.action_type] || red.action_type}
                      </TableCell>
                      <TableCell>
                        {rewardsLoading ? (
                          <Skeleton className="h-8 w-full md:max-w-56" />
                        ) : twitchRewards.length === 0 ? (
                          <span className="text-sub text-muted-foreground">
                            請先在 Twitch 建立自訂獎勵
                          </span>
                        ) : (
                          <Select
                            value={red.reward_name || '__none__'}
                            onValueChange={v => onRewardSelect(red, v === '__none__' ? '' : v)}
                          >
                            <SelectTrigger size="sm" className="w-full md:max-w-56">
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
                      </TableCell>
                      <TableCell className="text-center">
                        <Switch
                          aria-label={`啟用 ${ACTION_TYPE_LABELS[red.action_type] ?? red.action_type}`}
                          checked={red.enabled}
                          onCheckedChange={() => onToggle(red)}
                        />
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </TableShell>
          )}
        </CardContent>
      </Card>
    </SlideUp>
  )
}
