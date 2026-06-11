import { Link, useNavigate } from 'react-router-dom'

import avatarSrc from '@/assets/images/Avatar.png'
import { useTheme } from '@/components/layout/theme-provider'
import { Icon } from '@/components/primitives'
import {
  FadeIn,
  FadeInZoom,
  SlideUp,
  SlideUpSm,
  Stagger,
  StaggerItem,
} from '@/components/primitives'
import { Badge, Button } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const FEATURES = [
  {
    icon: 'fa-solid fa-terminal',
    title: '自訂指令與觸發器',
    desc: '設好指令，觀眾直接呼叫。支援關鍵字自動回應、使用間隔與開放對象設定，你專心直播就好。',
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '事件自動回應',
    desc: '有人追蹤、訂閱、突襲或兌換點數時，自動發出你設定好的訊息，一個都不漏。',
  },
  {
    icon: 'fa-solid fa-clock',
    title: '定時訊息',
    desc: '定時廣播頻道資訊或活動公告，沒人聊天時不打擾。',
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '遊戲排隊系統',
    desc: '管理觀眾排隊上下車、批次叫號，隊伍狀況同步顯示在直播畫面上。',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-film',
    title: '影片排隊系統',
    desc: '支援 YouTube、Bilibili、Twitch Clip，觀眾投稿後自動排隊依序播放。',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-chart-line',
    title: '數據分析',
    desc: '依時間區間查看聊天量趨勢與最活躍觀眾排名，掌握頻道互動概況。',
  },
]

const DISCORD_FEATURES = [
  {
    icon: 'fa-brands fa-instagram',
    title: '社群連結預覽',
    desc: '有人分享 Instagram、Bilibili、TikTok、Threads 或 Twitch 連結，Bot 自動顯示預覽。',
  },
  {
    icon: 'fa-solid fa-scroll',
    title: '伺服器事件日誌',
    desc: '誰刪了訊息、誰的身份被調整，全部自動記錄在你指定的頻道裡。',
  },
  {
    icon: 'fa-solid fa-stars',
    title: '娛樂與占卜',
    desc: '每日運勢、塔羅牌、TFT 戰棋段位查詢、AI 對話，讓伺服器氣氛活絡起來。',
  },
  {
    icon: 'fa-solid fa-gift',
    title: '生日追蹤 & 抽獎',
    desc: '成員登錄生日後 Bot 在當天自動送出祝賀，搭配抽獎功能讓活動更熱鬧。',
  },
]

const BUILTIN_COMMANDS = [
  { name: '!hi', desc: '確認機器人目前上線並回應' },
  { name: '!help', desc: '顯示頻道所有可用指令' },
  { name: '!ai', desc: '向 AI 提問，例：!ai 今天吃什麼' },
  { name: '!tft', desc: '查詢聯盟戰棋排名' },
  { name: '!運勢', desc: '抽取今日運勢' },
  { name: '!塔羅', desc: '塔羅牌占卜，可指定感情 / 事業 / 財運' },
  { name: '!開播時間', desc: '查看目前已開播多久' },
  { name: '!斥責', desc: '宣讀頻道對惡意言論的立場聲明' },
]

export default function Home() {
  useDocumentTitle('泥爸')
  const navigate = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <div className="min-h-screen overflow-x-hidden bg-background text-foreground select-none">
      {/* Theme toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-4 top-4 z-raised"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>

      <div className="mx-auto max-w-screen-2xl">
        {/* Hero — stacked on mobile/sm, side-by-side from md */}
        <section className="flex min-h-[60vh] flex-col items-center justify-center gap-8 px-6 py-12 text-center sm:gap-10 sm:px-10 sm:py-20 md:flex-row md:items-center md:gap-16 md:text-left lg:px-16 lg:py-24">
          {/* Avatar */}
          <FadeInZoom className="shrink-0">
            <div className="h-40 w-40 overflow-hidden rounded-full border-4 border-primary shadow-2xl sm:h-48 sm:w-48 lg:h-56 lg:w-56">
              <img
                src={avatarSrc}
                alt="Niibot 頭像"
                draggable="false"
                className="h-full w-full object-cover"
              />
            </div>
          </FadeInZoom>

          {/* Text */}
          <SlideUp delay={0.15} className="flex flex-col items-center md:items-start">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-7xl">Niibot</h1>
            <p className="mt-3 text-section-title text-muted-foreground">
              Twitch 聊天機器人 | 泥爸
            </p>
            <p className="mt-6 max-w-xl text-content leading-relaxed text-muted-foreground sm:text-lg">
              大家好，我是 Niibot，一名沒有勞基法保障的虛擬社畜。
            </p>
            <p className="mt-2 max-w-xl text-content leading-relaxed text-muted-foreground sm:text-lg">
              我沒有薪水，沒有休假，只有一個使命：
              <strong className="text-foreground">讓你的聊天室繼續活著。</strong>
            </p>
            <Button className="mt-8 h-12 px-10 text-content" onClick={() => navigate('/login')}>
              開始使用
            </Button>
          </SlideUp>
        </section>

        <div className="border-t border-border" />

        {/* Features */}
        <section className="px-6 py-10 sm:px-10 sm:py-16 lg:px-16">
          <SlideUpSm inView className="mb-3 text-page-title font-semibold sm:text-3xl">
            我能幫你做什麼
          </SlideUpSm>
          <FadeIn inView delay={0.1} className="mb-10 text-card-title text-muted-foreground">
            讓你專心直播，雜事交給我。
          </FadeIn>

          <Stagger inView className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(item => (
              <StaggerItem
                key={item.title}
                className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-sm sm:p-6"
              >
                <div className="flex items-center gap-3">
                  <Icon icon={item.icon} wrapperClassName="size-5 text-primary shrink-0" />
                  <span className="text-content font-semibold text-foreground">{item.title}</span>
                  {item.badge && (
                    <Badge variant="secondary" className="ml-auto text-label">
                      {item.badge}
                    </Badge>
                  )}
                </div>
                <p className="text-sub leading-relaxed text-muted-foreground">{item.desc}</p>
              </StaggerItem>
            ))}
          </Stagger>
        </section>

        <div className="border-t border-border" />

        {/* Commands + usage + CTA */}
        <section className="space-y-10 px-6 py-10 sm:px-10 sm:py-14 lg:px-16">
          <div>
            <SlideUpSm inView className="mb-2 text-section-title font-semibold sm:text-2xl">
              內建指令
            </SlideUpSm>
            <FadeIn inView delay={0.1} className="mb-6 text-content text-muted-foreground">
              開箱即用，無需設定。
            </FadeIn>

            <Stagger
              inView
              staggerChildren={0.05}
              className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4"
            >
              {BUILTIN_COMMANDS.map(cmd => (
                <StaggerItem
                  key={cmd.name}
                  className="flex flex-col gap-1.5 rounded-xl border bg-card px-4 py-3"
                >
                  <span className="font-mono text-sub font-semibold text-primary">{cmd.name}</span>
                  <span className="text-label leading-relaxed text-muted-foreground">
                    {cmd.desc}
                  </span>
                </StaggerItem>
              ))}
            </Stagger>
          </div>
        </section>

        <div className="border-t border-border" />

        {/* Discord */}
        <section className="px-6 py-10 sm:px-10 sm:py-16 lg:px-16">
          <div className="mb-3 flex items-center gap-3">
            <SlideUpSm inView className="text-page-title font-semibold sm:text-3xl">
              Discord 也顧到了
            </SlideUpSm>
            <FadeIn inView delay={0.1}>
              <Icon icon="fa-brands fa-discord" wrapperClassName="size-6 text-discord" />
            </FadeIn>
          </div>
          <FadeIn inView delay={0.15} className="mb-10 text-card-title text-muted-foreground">
            同一套系統，同時服務你的 Discord 伺服器。
          </FadeIn>

          <Stagger inView className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {DISCORD_FEATURES.map(item => (
              <StaggerItem
                key={item.title}
                className="flex flex-col gap-3 rounded-xl border bg-card p-4 shadow-sm sm:p-6"
              >
                <div className="flex items-center gap-3">
                  <Icon icon={item.icon} wrapperClassName="size-5 text-discord shrink-0" />
                  <span className="text-content font-semibold text-foreground">{item.title}</span>
                </div>
                <p className="text-sub leading-relaxed text-muted-foreground">{item.desc}</p>
              </StaggerItem>
            ))}
          </Stagger>
        </section>

        {/* Footer */}
        <div className="border-t border-border px-6 py-4 sm:px-10 sm:py-6 lg:px-16">
          <div className="flex flex-wrap items-center justify-between gap-4 text-label text-muted-foreground">
            <span>© {new Date().getFullYear()} Niibot</span>
            <div className="flex gap-4">
              <Link to="/terms" className="hover:text-foreground hover:underline">
                服務條款
              </Link>
              <Link to="/privacy" className="hover:text-foreground hover:underline">
                隱私權政策
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
