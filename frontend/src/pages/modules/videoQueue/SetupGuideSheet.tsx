import { GuideValue, type SetupStep, SetupSteps } from '@/components/SetupSteps'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
} from '@/components/ui'

const STEPS: SetupStep[] = [
  {
    icon: 'fa-brands fa-twitch',
    title: 'Twitch 新增獎勵',
    description: '觀眾點播的入口。',
    items: ['後台 → 社群 → 忠誠點數 → 管理獎勵', '新增自訂獎勵，設定名稱與點數', '確認已啟用'],
  },
  {
    icon: 'fa-solid fa-bolt',
    title: 'Events 綁定兌換',
    description: '把獎勵接到影片佇列。',
    items: ['Events → 忠誠點數兌換', '「播放清單」列選剛建立的獎勵', '打開狀態開關'],
  },
  {
    icon: 'fa-solid fa-display',
    title: 'OBS 加入畫面',
    description: '影片自動播放，沒有時透明。',
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

export function SetupGuideSheet({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Video Queue 使用說明</SheetTitle>
          <SheetDescription>在 Twitch 設定獎勵，再把畫面加進 OBS</SheetDescription>
        </SheetHeader>
        <SheetSection title="設定步驟" className="flex-1 overflow-y-auto">
          <SetupSteps steps={STEPS} />
        </SheetSection>
      </SheetContent>
    </Sheet>
  )
}
