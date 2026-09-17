import { Link } from 'react-router-dom'
import { MotionConfig } from 'motion/react'

import avatarSrc from '@/assets/images/Avatar.png'
import { useTheme } from '@/components/layout/theme-provider'
import { FadeIn, FadeInZoom, Icon, SlideUp, SlideUpSm } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

import overlayStyles from './VideoQueueOverlay.module.css'

const CAPABILITY_GROUPS = [
  {
    icon: 'fa-solid fa-terminal',
    title: 'Twitch 聊天室',
    description: '設定指令與自動回覆，讓聊天室互動更省心。',
    items: ['自訂指令', '自動回覆', '定時訊息', 'AI 聊天助理'],
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '直播工具',
    description: '需要時再加入遊戲、影片等直播工具。',
    items: ['遊戲排隊', '互動數據分析', '準星收藏', '贊助斗內'],
  },
  {
    icon: 'fa-brands fa-discord',
    title: 'Discord 社群',
    description: '需要時，讓 Discord 協助社群互動。',
    items: ['連結預覽', '社群活動紀錄', '生日提醒與抽獎', '娛樂與占卜'],
  },
]

const BUILTIN_COMMANDS = [
  { name: '!ai 今天吃什麼', response: '今天適合吃一碗不加班的牛肉麵。' },
  { name: '!開播時間', response: '這場直播已經進行 2 小時 18 分鐘。' },
]

const QUEUE_ITEMS = [
  { title: '下班後的深夜歌單', requester: 'momo', source: '聊天', duration: '3:42' },
  { title: '本週精彩 Twitch Clip', requester: 'yuki', source: '兌換', duration: '0:38' },
]

const SLIDE_CLASS = 'min-h-full snap-start snap-always'

function FlowItem({ icon, title }: { icon: string; title: string }) {
  return (
    <li className="grid grid-cols-1 place-items-center gap-element text-center sm:grid-cols-[2rem_minmax(0,1fr)] sm:justify-items-start sm:text-left">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary">
        <Icon icon={icon} size="sm" />
      </span>
      <span className="text-label leading-tight font-semibold text-foreground sm:text-sub">
        {title}
      </span>
    </li>
  )
}

function OverlayPreview() {
  const remaining = '03:42'

  return (
    <div aria-label="直播畫面顯示範例" className="min-w-0">
      <div className={overlayStyles.overlay} style={{ width: '100%', animation: 'none' }}>
        <div className={overlayStyles.titleBar} style={{ animation: 'none' }}>
          <div className={overlayStyles.titleLeft}>
            <span className={overlayStyles.titleName}>@ momo</span>
          </div>
          <div className={overlayStyles.controls} aria-label={`剩餘時間 ${remaining}`}>
            {Array.from(remaining).map((char, index) => (
              <span
                key={`${char}-${index}`}
                aria-hidden="true"
                className={char === ':' ? overlayStyles.charBoxNarrow : overlayStyles.charBox}
              >
                {char}
              </span>
            ))}
          </div>
        </div>
        <div className={overlayStyles.videoPanel}>
          <div className={overlayStyles.progressBar}>
            <div className={overlayStyles.progressFill} style={{ width: '38%' }} />
          </div>
          <img
            src="/images/valorant_map.jpg"
            alt="直播畫面上的影片內容示意"
            className={`${overlayStyles.videoContainer} h-full w-full object-cover`}
          />
          <div className={overlayStyles.sunkenOverlay} />
        </div>
      </div>
    </div>
  )
}

function VideoQueueSlide() {
  return (
    <section
      id="video-queue"
      data-testid="landing-slide"
      aria-label="影片點播管理功能展示"
      className={`${SLIDE_CLASS} flex items-center border-t`}
    >
      <div className="mx-auto w-full max-w-6xl px-page py-card sm:py-empty lg:px-page-lg">
        <SlideUpSm
          inView
          className="grid gap-section md:grid-cols-[minmax(0,1fr)_auto] md:items-end"
        >
          <div>
            <h2
              aria-label="影片點播管理"
              className="text-marketing-title font-semibold tracking-tight"
            >
              影片點播管理 <span aria-hidden="true">（Video Queue）</span>
            </h2>
            <p className="mt-element max-w-[65ch] text-content leading-relaxed text-muted-foreground">
              需要時再啟用：觀眾可透過聊天室連結或忠誠點數點播影片；你可調整播放順序並顯示在直播畫面。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-element md:justify-end">
            <Badge variant="secondary">YouTube</Badge>
            <Badge variant="secondary">Bilibili</Badge>
            <Badge variant="secondary">Twitch Clip</Badge>
          </div>
        </SlideUpSm>

        <SlideUpSm inView delay={0.05} className="mt-card">
          <ol className="grid grid-cols-3 gap-element border-y py-section sm:gap-card">
            <FlowItem icon="fa-solid fa-bolt" title="觀眾點播" />
            <FlowItem icon="fa-solid fa-sliders" title="管理播放順序" />
            <FlowItem icon="fa-solid fa-display" title="顯示在直播畫面" />
          </ol>
        </SlideUpSm>

        <FadeIn inView delay={0.1} className="mt-card">
          <Card className="overflow-hidden py-0 shadow-lg">
            <CardHeader className="items-center border-b py-section">
              <CardTitle className="flex min-w-0 items-center gap-element">
                等待佇列
                <Badge variant="outline" className="h-5 py-0 leading-none">
                  示意畫面
                </Badge>
              </CardTitle>
              <CardAction className="self-center">
                <span className="text-label leading-none text-muted-foreground">
                  待播 2 首 · 4:20
                </span>
              </CardAction>
            </CardHeader>
            <CardContent
              data-testid="video-queue-layout"
              className="grid gap-0 p-0 lg:grid-cols-[minmax(0,1.2fr)_minmax(22rem,0.8fr)]"
            >
              <div aria-label="等待佇列示意" className="min-w-0 px-card">
                <div className="divide-y">
                  {QUEUE_ITEMS.map((item, index) => (
                    <div
                      key={item.title}
                      className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-section py-section"
                    >
                      <Badge
                        variant={index === 0 ? 'default' : 'outline'}
                        className="size-6 p-0 leading-none tabular-nums"
                      >
                        {index + 1}
                      </Badge>
                      <div className="min-w-0">
                        <p className="truncate text-content font-medium">{item.title}</p>
                        <p className="mt-1 truncate text-label text-muted-foreground">
                          {item.requester} · {item.source}
                        </p>
                      </div>
                      <span className="text-sub tabular-nums text-muted-foreground">
                        {item.duration}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto] items-center gap-section border-t bg-muted/40 p-section lg:grid-cols-1 lg:border-t-0 lg:border-l lg:p-card">
                <OverlayPreview />
                <div className="min-w-0 lg:mt-section">
                  <p className="text-label text-muted-foreground">正在播放</p>
                  <p className="mt-1 truncate text-sub font-semibold">深夜聊天室精華</p>
                  <p className="mt-1 text-label text-muted-foreground">momo · 03:42</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </FadeIn>
      </div>
    </section>
  )
}

function ChatSlide() {
  return (
    <section data-testid="landing-slide" className={`${SLIDE_CLASS} flex items-center border-t`}>
      <div className="mx-auto grid w-full max-w-6xl gap-card px-page py-card sm:py-empty lg:grid-cols-2 lg:items-center lg:gap-empty lg:px-page-lg">
        <SlideUpSm inView>
          <h2 className="text-marketing-title font-semibold tracking-tight">聊天室互動</h2>
          <p className="mt-element max-w-[60ch] text-content leading-relaxed text-muted-foreground">
            設定指令回覆，也可在追隨、訂閱、突襲或忠誠點數兌換時自動回覆。
          </p>
          <div className="mt-section flex flex-wrap gap-element">
            <Badge variant="outline">指令回覆</Badge>
            <Badge variant="outline">最低權限</Badge>
            <Badge variant="outline">冷卻</Badge>
            <Badge variant="outline">事件回覆</Badge>
          </div>
        </SlideUpSm>

        <FadeIn inView delay={0.1}>
          <Card className="overflow-hidden py-0 shadow-md">
            <CardHeader className="items-center border-b py-section">
              <CardTitle className="flex min-w-0 items-center gap-element">
                <Icon icon="fa-solid fa-terminal" size="sm" wrapperClassName="text-primary" />
                回應示意
              </CardTitle>
              <CardAction className="self-center">
                <Badge variant="secondary" className="h-5 py-0 leading-none">
                  即時
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent className="divide-y p-0">
              {BUILTIN_COMMANDS.map(command => (
                <div
                  key={command.name}
                  className="grid items-baseline gap-element p-card sm:grid-cols-[8.5rem_1fr]"
                >
                  <code className="text-sub leading-relaxed font-semibold text-primary">
                    {command.name}
                  </code>
                  <p className="text-sub leading-relaxed text-muted-foreground">
                    {command.response}
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        </FadeIn>
      </div>
    </section>
  )
}

function OtherFeaturesSlide() {
  return (
    <section data-testid="landing-slide" className={`${SLIDE_CLASS} flex flex-col border-t`}>
      <div className="mx-auto flex w-full max-w-6xl flex-1 items-center px-page py-card sm:py-empty lg:px-page-lg">
        <div className="w-full">
          <SlideUpSm inView>
            <h2 className="text-marketing-title font-semibold tracking-tight">依需求加入的工具</h2>
            <p className="mt-element max-w-[60ch] text-content leading-relaxed text-muted-foreground">
              先設定 Twitch 聊天室，再依需求加入直播與 Discord 工具。
            </p>
          </SlideUpSm>

          <FadeIn inView delay={0.08} className="mt-card grid border-y lg:grid-cols-3">
            {CAPABILITY_GROUPS.map((group, index) => (
              <article
                key={group.title}
                className={`py-card lg:px-card ${index > 0 ? 'border-t lg:border-t-0 lg:border-l' : ''}`}
              >
                <div className="flex items-center gap-section">
                  <Icon
                    icon={group.icon}
                    size="xl"
                    wrapperClassName={group.title === '社群延伸' ? 'text-discord' : 'text-primary'}
                  />
                  <div>
                    <h3 className="text-section-title font-semibold">{group.title}</h3>
                    <p className="mt-1 text-sub text-muted-foreground">{group.description}</p>
                  </div>
                </div>
                <ul className="mt-section grid grid-cols-2 gap-x-section gap-y-element lg:grid-cols-1">
                  {group.items.map(item => (
                    <li key={item} className="flex items-center gap-element text-sub">
                      <span
                        className="size-1.5 shrink-0 rounded-full bg-primary"
                        aria-hidden="true"
                      />
                      {item}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </FadeIn>
        </div>
      </div>

      <footer className="border-t">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-section px-page py-section text-label text-muted-foreground lg:px-page-lg">
          <span>© {new Date().getFullYear()} Niibot</span>
          <div className="flex gap-card">
            <Link to="/terms" className="underline-offset-4 hover:text-foreground hover:underline">
              服務條款
            </Link>
            <Link
              to="/privacy"
              className="underline-offset-4 hover:text-foreground hover:underline"
            >
              隱私權政策
            </Link>
          </div>
        </div>
      </footer>
    </section>
  )
}

export default function Landing() {
  useDocumentTitle('泥爸')
  const { resolvedTheme, setTheme } = useTheme()
  const nextTheme = resolvedTheme === 'dark' ? 'light' : 'dark'

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-svh flex-col overflow-hidden bg-background text-content text-foreground">
        <header className="z-sticky shrink-0 border-b bg-background">
          <nav
            aria-label="主要導覽"
            className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-section px-page lg:px-page-lg"
          >
            <Link
              to="/"
              className="flex min-w-0 items-center gap-element rounded-md focus-visible:ring-2"
            >
              <img
                src={avatarSrc}
                alt=""
                draggable="false"
                className="size-8 rounded-full border object-cover"
              />
              <span className="truncate text-content font-semibold">Niibot</span>
            </Link>
            <div className="flex items-center gap-element">
              <Button
                variant="ghost"
                size="icon"
                aria-label={`切換至${nextTheme === 'light' ? '淺色' : '深色'}主題`}
                onClick={() => setTheme(nextTheme)}
              >
                <Icon icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'} />
              </Button>
              <Button asChild>
                <Link to="/login">
                  開始使用
                  <Icon icon="fa-solid fa-arrow-right" size="sm" />
                </Link>
              </Button>
            </div>
          </nav>
        </header>

        <main
          data-testid="landing-deck"
          className="min-h-0 flex-1 snap-y snap-mandatory overflow-y-auto overscroll-y-contain"
        >
          <section data-testid="landing-slide" className={`${SLIDE_CLASS} flex items-center`}>
            <div className="mx-auto grid w-full max-w-6xl items-center gap-card px-page py-card md:grid-cols-[minmax(0,1fr)_auto] lg:gap-empty lg:px-page-lg">
              <SlideUp className="max-w-2xl">
                <h1 className="text-display font-bold tracking-tight">Niibot</h1>
                <p className="mt-element text-section-title text-muted-foreground">
                  Twitch 直播聊天室的小幫手｜泥爸
                </p>
                <p className="mt-1 text-content text-muted-foreground">
                  先設定指令與自動回覆；其他直播與 Discord 工具可依需求加入。
                </p>
                <p className="mt-card max-w-[46ch] text-content leading-relaxed text-muted-foreground sm:text-card-title">
                  <span className="block">沒有勞基法保障的虛擬社畜。</span>
                  <span className="mt-element block">沒有薪水，沒有休假，只有一個使命：</span>
                  <strong className="mt-1 block font-semibold text-foreground">
                    讓你的聊天室繼續活著。
                  </strong>
                </p>
                <Button asChild size="lg" className="mt-card">
                  <Link to="/login">
                    開始使用
                    <Icon icon="fa-solid fa-arrow-right" size="sm" />
                  </Link>
                </Button>
              </SlideUp>

              <FadeInZoom delay={0.15} className="mx-auto md:mx-0">
                <div className="size-40 overflow-hidden rounded-full border-4 border-primary shadow-lg sm:size-52 lg:size-72">
                  <img
                    src={avatarSrc}
                    alt="Niibot 泥爸頭像"
                    draggable="false"
                    className="h-full w-full object-cover"
                  />
                </div>
              </FadeInZoom>
            </div>
          </section>

          <ChatSlide />
          <VideoQueueSlide />
          <OtherFeaturesSlide />
        </main>
      </div>
    </MotionConfig>
  )
}
