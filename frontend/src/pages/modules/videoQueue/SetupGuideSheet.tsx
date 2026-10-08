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

// Compact CTA beside a step title: the badge's 28px height and label-size
// text, in the primary colour so it clearly reads as clickable.
const STEP_CTA = 'h-7 px-2.5 text-label'

// Order: ① dependencies (the reward must exist on Twitch before Niibot can
// bind it) → ② set everything up before switching it on (the master 啟用 is
// the very last item) → ③ this page before steps that leave it.
function buildSteps(twitchRewardsUrl: string, onNavigate: () => void): SetupStep[] {
  return [
    {
      icon: 'fa-solid fa-display',
      title: 'OBS 加入畫面',
      description: '沒有播放時畫面透明。',
      items: [
        <>
          把「OBS 畫面」網址左側的把手拖進 OBS（或複製網址，新增「瀏覽器」來源，
          <GuideValue>640 × 400</GuideValue>）
        </>,
        <>
          來源屬性勾選 <GuideValue>使用 OBS 控制音訊</GuideValue>
        </>,
        <>
          混音器設為 <GuideValue>監聽並輸出</GuideValue>
        </>,
        <>
          不要勾選 <GuideValue>不可見時關閉來源</GuideValue>，切換場景才不會重新載入、跳過片段
        </>,
        <>
          若影片畫面偶爾卡住：OBS「設定 → 進階」取消 <GuideValue>啟用瀏覽器來源硬體加速</GuideValue>
          並重開 OBS
        </>,
      ],
    },
    {
      icon: 'fa-brands fa-twitch',
      title: '在 Twitch 建立獎勵',
      items: [
        '新增並啟用自訂獎勵，設定名稱與點數',
        <>
          勾選「需要觀眾輸入文字」，說明可填{' '}
          <GuideValue>
            貼上影片網址（YouTube、Twitch、Bilibili、Instagram），可於網址後加上播放片段，例：1:30-4:00
          </GuideValue>
        </>,
      ],
      action: (
        <Button size="sm" className={STEP_CTA} asChild>
          <a href={twitchRewardsUrl} target="_blank" rel="noopener noreferrer">
            <Icon icon="fa-solid fa-arrow-up-right-from-square" wrapperClassName="size-3" />
            Twitch
          </a>
        </Button>
      ),
    },
    {
      icon: 'fa-solid fa-link',
      title: '綁定獎勵',
      items: [
        <>
          <GuideValue>播放清單</GuideValue> 選擇剛建立的獎勵並啟用
        </>,
      ],
      action: (
        <Button size="sm" className={STEP_CTA} asChild onClick={onNavigate}>
          <Link to="/channel-points">
            <Icon icon="fa-solid fa-arrow-right" wrapperClassName="size-3" />
            忠誠點數
          </Link>
        </Button>
      ),
    },
    {
      icon: 'fa-solid fa-sliders',
      title: '開啟點播',
      items: [
        <>
          「點播設定 → 加入來源」打開 <GuideValue>開放忠誠點數點播</GuideValue>
        </>,
        <>
          本頁右上角打開 <GuideValue>啟用</GuideValue>
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
          <SheetDescription>四個步驟完成設定</SheetDescription>
        </SheetHeader>
        <SheetSection title="設定步驟" className="flex-1 overflow-y-auto">
          <SetupSteps steps={buildSteps(twitchRewardsUrl, () => onOpenChange(false))} />
        </SheetSection>
      </SheetContent>
    </Sheet>
  )
}
