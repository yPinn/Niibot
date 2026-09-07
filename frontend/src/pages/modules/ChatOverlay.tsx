import { useCallback, useEffect, useMemo, useState } from 'react'

import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { OverlayUrlBlock } from '@/components/OverlayUrlBlock'
import { Icon, OptionPicker, SlideUp } from '@/components/primitives'
import { GuideValue, type SetupStep, SetupSteps } from '@/components/SetupSteps'
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Switch,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { copyToClipboard } from '@/lib/clipboard'

import { ChatPreview } from './chatOverlay/ChatPreview'
import { CssHighlight } from './chatOverlay/CssHighlight'
import {
  ALIGN_OPTIONS,
  ANIM_DIR_OPTIONS,
  BADGE_FILTER_OPTIONS,
  FONT_SIZE_STEPS,
  MSG_BG_OPTIONS,
  SPACING_STEPS,
} from './chatOverlay/options'
import { StepSlider } from './chatOverlay/SettingsControls'
import { type ChatCssSettings, generateCss, loadSettings, saveSettings } from './chatOverlayCss'

const HELP_STEPS: SetupStep[] = [
  {
    icon: 'fa-solid fa-palette',
    title: '調整樣式',
    description: '右側調整，左側即時預覽。',
    items: [
      '外觀：背景、訊息樣式、對齊方向',
      '文字：字型大小與行間距',
      '顯示：標題列、徽章、文字陰影',
      '動畫：進場方向',
    ],
  },
  {
    icon: 'fa-solid fa-code',
    title: '複製 CSS',
    description: '產生的 CSS 要貼進 OBS。',
    items: [
      <>
        切換到 <GuideValue>CSS</GuideValue> 分頁
      </>,
      '點「複製 CSS」',
    ],
  },
  {
    icon: 'fa-solid fa-display',
    title: 'OBS 加入畫面',
    description: '透明疊在直播畫面上。',
    items: [
      'OBS 加「瀏覽器」來源',
      'URL 填下方的聊天室連結',
      <>
        CSS 貼進 <GuideValue>自訂 CSS</GuideValue> 欄位
      </>,
      <>
        建議尺寸 <GuideValue>360 × 640</GuideValue>
      </>,
    ],
  },
]

export default function ChatOverlayModule() {
  useDocumentTitle('Chat Overlay')

  const { user } = useAuth()
  const [settings, setSettings] = useState<ChatCssSettings>(loadSettings)
  const [rightPanel, setRightPanel] = useState<'preview' | 'css'>('preview')
  const [settingsOpen, setSettingsOpen] = useState(false)

  const patch = useCallback((partial: Partial<ChatCssSettings>) => {
    setSettings(prev => {
      const next = { ...prev, ...partial }
      // text shadow only applies to transparent backgrounds — reset when leaving transparent
      if (partial.background && partial.background !== 'transparent') next.textShadow = false
      return next
    })
  }, [])

  useEffect(() => {
    saveSettings(settings)
  }, [settings])

  const css = useMemo(() => generateCss(settings), [settings])

  const copyCss = () => copyToClipboard(css, 'CSS 已複製', '複製失敗，請手動選取')

  const twitchUrl = user?.name ? `https://www.twitch.tv/popout/${user.name}/chat` : ''

  return (
    <PageMain>
      <PageHeader
        title="Chat Overlay"
        description="自訂 Twitch 聊天室樣式，貼入 OBS Browser Source"
      >
        <Button
          variant="ghost"
          size="icon"
          className="mt-0.5 shrink-0 border border-primary/40 text-muted-foreground hover:border-primary hover:text-primary/80"
          onClick={() => setSettingsOpen(true)}
          title="使用說明"
        >
          <Icon
            icon="fa-regular fa-circle-question"
            wrapperClassName="size-5"
            className="text-content"
          />
        </Button>
      </PageHeader>

      {/* Help sheet */}
      <Sheet open={settingsOpen} onOpenChange={setSettingsOpen}>
        <SheetContent side="right">
          <SheetHeader>
            <SheetTitle>Chat Overlay 使用說明</SheetTitle>
            <SheetDescription>如何在 OBS 套用自訂聊天室樣式</SheetDescription>
          </SheetHeader>
          <SheetSection title="設定步驟" className="flex-1 overflow-y-auto">
            <SetupSteps steps={HELP_STEPS} />
          </SheetSection>
        </SheetContent>
      </Sheet>

      <SlideUp
        inView
        delay={0.05}
        className="grid grid-cols-1 lg:grid-cols-12 gap-section items-start"
      >
        {/* Left: switchable Preview / CSS */}
        <div className="lg:col-span-6 flex flex-col gap-element min-w-0">
          {/* Tab bar */}
          <div className="flex shrink-0 items-center">
            <div className="flex gap-1 rounded-lg border p-1">
              {(['preview', 'css'] as const).map(panel => (
                <button
                  key={panel}
                  type="button"
                  onClick={() => setRightPanel(panel)}
                  className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sub font-medium transition-colors ${
                    rightPanel === panel
                      ? 'bg-card text-foreground shadow-sm'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon
                    icon={panel === 'preview' ? 'fa-solid fa-eye' : 'fa-solid fa-code'}
                    className="text-label"
                  />
                  {panel === 'preview' ? '預覽' : 'CSS'}
                </button>
              ))}
            </div>
          </div>

          {/* Panel content */}
          {rightPanel === 'preview' ? (
            <>
              <div className="flex justify-center">
                <div
                  className="overflow-hidden rounded-lg border w-full max-w-[360px]"
                  style={{ aspectRatio: '360/640' }}
                >
                  <ChatPreview s={settings} />
                </div>
              </div>
              {twitchUrl && <OverlayUrlBlock url={twitchUrl} />}
            </>
          ) : (
            <div className="h-[462px] overflow-auto rounded-lg border bg-muted p-4">
              <CssHighlight code={css} />
            </div>
          )}
        </div>

        {/* Right: Settings */}
        <div className="lg:col-span-6 flex flex-col gap-section">
          <Card>
            <CardHeader className="flex flex-row items-start justify-between gap-2">
              <div className="flex flex-col gap-1">
                <CardTitle>樣式設定</CardTitle>
                <CardDescription>調整後自動產生 CSS，無需儲存</CardDescription>
              </div>
              <Button onClick={copyCss} size="sm" className="shrink-0">
                <Icon icon="fa-regular fa-copy" className="mr-1.5 text-label" />
                複製 CSS
              </Button>
            </CardHeader>
            <CardContent className="flex flex-col gap-section">
              {/* ── 外觀 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">外觀</p>
                <div className="flex flex-col gap-2">
                  <Label>背景</Label>
                  <div className="flex items-center gap-2">
                    {(['transparent', 'color'] as const).map(opt => (
                      <button
                        key={opt}
                        type="button"
                        onClick={() => patch({ background: opt })}
                        className={`select-none rounded-md border px-3 py-1.5 text-sub font-medium transition-colors ${
                          settings.background === opt
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'hover:bg-accent'
                        }`}
                      >
                        {opt === 'transparent' ? '透明' : '顏色'}
                      </button>
                    ))}
                    {settings.background === 'color' && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <label className="cursor-pointer select-none">
                            <span
                              className="block w-7 h-7 rounded-md border border-border transition-transform hover:scale-110"
                              style={{ background: settings.bgColor }}
                            />
                            <input
                              type="color"
                              value={settings.bgColor}
                              onChange={e => patch({ bgColor: e.target.value })}
                              className="sr-only"
                            />
                          </label>
                        </TooltipTrigger>
                        <TooltipContent>選擇背景顏色</TooltipContent>
                      </Tooltip>
                    )}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-section">
                  <OptionPicker
                    label="樣式"
                    options={MSG_BG_OPTIONS}
                    value={settings.messageBg}
                    onChange={v => patch({ messageBg: v })}
                  />
                  <OptionPicker
                    label="對齊"
                    options={ALIGN_OPTIONS}
                    value={settings.align}
                    onChange={v => patch({ align: v })}
                  />
                </div>
              </div>

              {/* ── 文字 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">文字</p>
                <div className="grid grid-cols-2 gap-section">
                  <StepSlider
                    label="大小"
                    steps={FONT_SIZE_STEPS}
                    value={settings.fontSize}
                    onChange={v => patch({ fontSize: v })}
                    unit="px"
                  />
                  <StepSlider
                    label="間距"
                    steps={SPACING_STEPS}
                    value={settings.spacing}
                    onChange={v => patch({ spacing: v })}
                  />
                </div>
              </div>

              {/* ── 顯示 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">顯示</p>
                <div className="flex flex-col gap-element">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="hideHeader">隱藏標題列</Label>
                    <Switch
                      id="hideHeader"
                      checked={settings.hideHeader}
                      onCheckedChange={v => patch({ hideHeader: v })}
                    />
                  </div>
                  <OptionPicker
                    label="徽章顯示"
                    options={BADGE_FILTER_OPTIONS}
                    value={settings.badgeFilter}
                    onChange={v => patch({ badgeFilter: v })}
                  />
                  {settings.background === 'transparent' && (
                    <div className="flex items-center justify-between">
                      <div>
                        <Label htmlFor="textShadow">文字陰影</Label>
                        <p className="text-muted-foreground mt-0.5 text-label">增強文字辨識度</p>
                      </div>
                      <Switch
                        id="textShadow"
                        checked={settings.textShadow}
                        onCheckedChange={v => patch({ textShadow: v })}
                      />
                    </div>
                  )}
                  <div className="flex items-center justify-between">
                    <div>
                      <Label htmlFor="hideBot">隱藏 Bot 訊息</Label>
                      <p className="text-muted-foreground mt-0.5 text-label">依機器人徽章過濾</p>
                    </div>
                    <Switch
                      id="hideBot"
                      checked={settings.hideBot}
                      onCheckedChange={v => patch({ hideBot: v })}
                    />
                  </div>
                </div>
              </div>

              {/* ── 動畫 ── */}
              <div className="flex flex-col gap-3">
                <p className="text-label font-medium text-muted-foreground">動畫</p>
                <div className="flex flex-col gap-element">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="animation">進場動畫</Label>
                    <Switch
                      id="animation"
                      checked={settings.animation}
                      onCheckedChange={v => patch({ animation: v })}
                    />
                  </div>
                  {settings.animation && (
                    <OptionPicker
                      label="方向"
                      options={ANIM_DIR_OPTIONS}
                      value={settings.animDir}
                      onChange={v => patch({ animDir: v })}
                      labelClassName="text-muted-foreground"
                    />
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </SlideUp>
    </PageMain>
  )
}
