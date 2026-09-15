import { Link } from 'react-router-dom'

import { Icon } from '@/components/primitives'
import { GuideValue, type SetupStep, SetupSteps } from '@/components/SetupSteps'
import {
  Button,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'

function buildSteps(twitchRewardsUrl: string, onNavigate: () => void): SetupStep[] {
  return [
    {
      icon: 'fa-brands fa-twitch',
      title: '在 Twitch 建立獎勵',
      description: '觀眾點播的入口，要先在 Twitch 那邊設定好。',
      items: ['新增自訂獎勵，設定名稱與點數', '確認獎勵已啟用'],
      action: (
        <Button variant="outline" size="sm" asChild>
          <a href={twitchRewardsUrl} target="_blank" rel="noopener noreferrer">
            <Icon icon="fa-brands fa-twitch" wrapperClassName="mr-1.5 size-3.5" />
            前往 Twitch 獎勵頁面
          </a>
        </Button>
      ),
    },
    {
      icon: 'fa-solid fa-link',
      title: '在 Niibot 綁定獎勵',
      description: '把剛剛建立的 Twitch 獎勵接到影片佇列。',
      items: [
        '「播放清單」列選擇剛建立的獎勵，打開狀態開關',
        <>
          回到本頁「點播規則」，打開 <GuideValue>開放用頻道點數兌換</GuideValue>
        </>,
        <>
          確認本頁右上角的 <GuideValue>啟用</GuideValue> 也已打開
        </>,
      ],
      action: (
        <Button variant="outline" size="sm" asChild onClick={onNavigate}>
          <Link to="/channel-points">
            <Icon icon="fa-solid fa-arrow-right" wrapperClassName="mr-1.5 size-3.5" />
            前往 Channel Points 頁面
          </Link>
        </Button>
      ),
    },
    {
      icon: 'fa-solid fa-display',
      title: 'OBS 加入畫面',
      description: '影片自動播放，沒有播放時透明。',
      items: [
        '複製「OBS 畫面」卡片的連結',
        <>
          OBS 加「瀏覽器」來源，貼上連結（<GuideValue>640 × 400</GuideValue>）
        </>,
        <>
          來源屬性勾選 <GuideValue>使用 OBS 控制音訊</GuideValue>
        </>,
        <>
          混音器開啟 <GuideValue>監聽並輸出</GuideValue>（預設靜音）
        </>,
      ],
    },
  ]
}

export function SetupGuideSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { user } = useAuth()
  const twitchRewardsUrl = user?.name
    ? `https://dashboard.twitch.tv/u/${user.name}/viewer-rewards/channel-points/rewards`
    : 'https://dashboard.twitch.tv/'

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Video Queue 使用說明</SheetTitle>
          <SheetDescription>在 Twitch 設定獎勵，在 Niibot 綁定，再把畫面加進 OBS</SheetDescription>
        </SheetHeader>
        <SheetSection title="設定步驟" className="flex-1 overflow-y-auto">
          <SetupSteps steps={buildSteps(twitchRewardsUrl, () => onOpenChange(false))} />
        </SheetSection>
      </SheetContent>
    </Sheet>
  )
}
