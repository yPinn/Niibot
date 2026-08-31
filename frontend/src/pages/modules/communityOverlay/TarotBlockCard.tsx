import type { ReactNode } from 'react'

import { Icon, Spinner } from '@/components/primitives'
import {
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
} from '@/components/ui'

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
        <CardHeader className="has-data-[slot=card-action]:grid-cols-1 sm:has-data-[slot=card-action]:grid-cols-[1fr_auto]">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <h3>每日塔羅</h3>
            <Badge variant="secondary">牌卡</Badge>
            <Badge variant={themeChanged ? 'secondary' : 'outline'}>{themeStatus}</Badge>
          </CardTitle>
          <CardDescription>觀眾抽牌時，直播畫面只播放牌面；完整解讀回覆在聊天室。</CardDescription>
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
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <p className="text-label text-muted-foreground">聊天指令</p>
              <p className="text-content font-semibold">!塔羅 [主題]</p>
              <p className="text-label text-muted-foreground">未填為綜合；另有感情、事業、財運</p>
            </div>
            <div className="space-y-1">
              <p className="text-label text-muted-foreground">主題規則</p>
              <p className="text-content font-semibold">每個主題每天固定一張</p>
              <p className="text-label text-muted-foreground">同一主題重查結果不變</p>
            </div>
            <div className="space-y-1">
              <p className="text-label text-muted-foreground">牌面來源</p>
              <p className="text-content font-semibold">本地版本化牌組</p>
              <p className="text-label text-muted-foreground">替換牌組不影響歷史事件</p>
            </div>
          </div>
        </CardContent>

        <CollapsibleContent>
          <div className="mt-section border-t px-card pt-card">{children}</div>
        </CollapsibleContent>
      </Card>
    </Collapsible>
  )
}
