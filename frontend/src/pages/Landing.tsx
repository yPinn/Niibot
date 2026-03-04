import { useNavigate } from 'react-router-dom'

import avatarSrc from '@/assets/images/Avatar.png'
import { useTheme } from '@/components/theme-provider'
import { Badge, Button, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const FEATURES = [
  {
    icon: 'fa-solid fa-terminal',
    title: '自訂指令與觸發器',
    desc: '設好指令，觀眾直接呼叫。支援關鍵字自動回應、冷卻時間與權限設定，你專心直播就好。',
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '事件自動回應',
    desc: '追蹤、訂閱、Raid、Bits、頻道點數兌換，全部自動觸發定制訊息，一個都不漏。',
  },
  {
    icon: 'fa-solid fa-clock',
    title: '定時訊息',
    desc: '定時廣播頻道資訊或活動公告。支援最低聊天門檻，冷場不打擾。',
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '遊戲排隊系統',
    desc: '管理觀眾上下車、批次叫號，OBS 疊加層即時顯示排隊狀況，直播畫面不跳出。',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-film',
    title: '影片排隊系統',
    desc: '觀眾用聊天、頻道點數或贊助投 YouTube 影片，按來源優先級自動排隊播放。',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-chart-line',
    title: '數據分析',
    desc: '30 天直播趨勢、聊天量、最活躍觀眾與最常用指令，掌握頻道成長一目了然。',
  },
]

const COMMANDS = ['!ai', '!運勢', '!help', '!vq', '!gq']

export default function Home() {
  useDocumentTitle('泥爸')
  const navigate = useNavigate()
  const { resolvedTheme, setTheme } = useTheme()

  return (
    <div className="min-h-screen overflow-x-hidden bg-background text-foreground">
      {/* Theme toggle */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed right-4 top-4 z-10"
        onClick={() => setTheme(resolvedTheme === 'dark' ? 'light' : 'dark')}
      >
        <Icon
          icon={resolvedTheme === 'dark' ? 'fa-solid fa-sun' : 'fa-solid fa-moon'}
          wrapperClassName=""
        />
      </Button>

      <div className="mx-auto max-w-screen-2xl">
        {/* Hero — stacked on mobile/sm, side-by-side from md */}
        <section className="flex min-h-[60vh] flex-col items-center justify-center gap-10 px-6 py-20 text-center sm:px-10 md:flex-row md:items-center md:gap-16 md:text-left lg:px-16 lg:py-24">
          {/* Avatar */}
          <div className="shrink-0">
            <div className="h-40 w-40 overflow-hidden rounded-full border-4 border-primary shadow-2xl sm:h-48 sm:w-48 lg:h-56 lg:w-56">
              <img src={avatarSrc} alt="Niibot 頭像" className="h-full w-full object-cover" />
            </div>
          </div>

          {/* Text */}
          <div className="flex flex-col items-center md:items-start">
            <h1 className="text-4xl font-bold tracking-tight sm:text-5xl lg:text-7xl">Niibot</h1>
            <p className="mt-3 text-xl text-muted-foreground">Twitch 聊天機器人 | 泥爸</p>
            <p className="mt-6 max-w-xl text-lg leading-relaxed text-muted-foreground">
              大家好，我是 Niibot，一名沒有勞基法保障的虛擬社畜。
            </p>
            <p className="mt-2 max-w-xl text-lg leading-relaxed text-muted-foreground">
              我沒有薪水，沒有休假，只有一個使命：
              <strong className="text-foreground">讓你的聊天室繼續活著。</strong>
            </p>
            <Button className="mt-8 h-12 px-10 text-base" onClick={() => navigate('/login')}>
              開始使用
            </Button>
          </div>
        </section>

        <div className="border-t border-border" />

        {/* Features */}
        <section className="px-6 py-16 sm:px-10 lg:px-16">
          <h2 className="mb-3 text-2xl font-semibold sm:text-3xl">我能幫你做什麼</h2>
          <p className="mb-10 text-lg text-muted-foreground">讓你專心直播，雜事交給我。</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(item => (
              <div
                key={item.title}
                className="flex flex-col gap-3 rounded-xl border bg-card p-6 shadow-sm"
              >
                <div className="flex items-center gap-3">
                  <Icon icon={item.icon} wrapperClassName="size-5 text-primary shrink-0" />
                  <span className="text-base font-semibold text-foreground">{item.title}</span>
                  {item.badge && (
                    <Badge variant="secondary" className="ml-auto text-xs">
                      {item.badge}
                    </Badge>
                  )}
                </div>
                <p className="text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
              </div>
            ))}
          </div>
        </section>

        <div className="border-t border-border" />

        {/* Commands + usage + CTA */}
        <section className="space-y-10 px-6 py-14 sm:px-10 lg:px-16">
          <div>
            <h2 className="mb-4 text-xl font-semibold sm:text-2xl">常用指令</h2>
            <div className="flex flex-wrap gap-2">
              {COMMANDS.map(cmd => (
                <Badge key={cmd} variant="secondary" className="px-3 py-1 font-mono text-sm">
                  {cmd}
                </Badge>
              ))}
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
