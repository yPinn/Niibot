import type { ReactNode } from 'react'

import { Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CARD_HEADER_STACK_ON_MOBILE,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui'

import { BlockInfoGrid } from './BlockInfoGrid'

interface TarotBlockCardProps {
  testing: boolean
  open: boolean
  themeStatus: string
  themeChanged: boolean
  onOpenChange: (open: boolean) => void
  onTest: () => void
  children: ReactNode
}

export function TarotBlockCard({
  testing,
  open,
  themeStatus,
  themeChanged,
  onOpenChange,
  onTest,
  children,
}: TarotBlockCardProps) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange}>
      <Card className="min-w-0">
        <CardHeader className={CARD_HEADER_STACK_ON_MOBILE}>
          <CardTitle className="flex flex-wrap items-center gap-2">
            <h3>每日塔羅</h3>
            <Badge variant="secondary">牌卡</Badge>
            <Badge variant={themeChanged ? 'secondary' : 'outline'}>{themeStatus}</Badge>
          </CardTitle>
          <CardDescription>直播顯示牌面，完整解讀回覆在聊天室。</CardDescription>
          <CardAction className="col-start-1 row-span-1 row-start-3 flex flex-wrap items-center justify-start gap-2 justify-self-stretch sm:col-start-2 sm:row-span-2 sm:row-start-1 sm:justify-end sm:justify-self-end">
            <Button
              size="sm"
              variant="outline"
              aria-label="測試每日塔羅動畫"
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
                aria-label={open ? '收合每日塔羅設定' : '展開每日塔羅設定'}
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
          <BlockInfoGrid
            className="sm:grid-cols-3"
            cells={[
              {
                label: '聊天指令',
                value: '!塔羅 [主題]',
                note: '未填為綜合；可選感情、事業、財運',
              },
              {
                label: '主題規則',
                value: '每個主題每天一張',
                note: '同主題重查結果不變',
              },
              {
                label: '牌面來源',
                value: '內建牌組',
                note: '更新不影響歷史紀錄',
              },
            ]}
          />
        </CardContent>

        <CollapsibleContent>
          <div className="mt-section border-t px-card pt-card">{children}</div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
