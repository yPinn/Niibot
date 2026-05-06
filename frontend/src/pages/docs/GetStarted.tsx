import { useState } from 'react'
import { Link } from 'react-router-dom'

import { DiscordHelpBanner } from '@/components/DiscordHelpBanner'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  SlideUp,
  SlideUpSm,
  Stagger,
  StaggerItem,
} from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type ChatBadge = 'broadcaster' | 'mod' | null

type ChatLine =
  | { type: 'message'; badge: ChatBadge; username: string; color: string; message: string }
  | { type: 'system'; message: string }

function ChatBadgeIcon({ badge }: { badge: ChatBadge }) {
  const base = 'inline-flex shrink-0 items-center justify-center size-5 rounded mr-1'
  if (badge === 'broadcaster') {
    return (
      <span className={`${base} bg-status-live`}>
        <i className="fa-solid fa-video text-xs text-white" />
      </span>
    )
  }
  if (badge === 'mod') {
    return (
      <span className={`${base} bg-status-online`}>
        <i className="fa-solid fa-sword text-xs text-white" />
      </span>
    )
  }
  return null
}

function TwitchChatMockup({
  channel,
  lines,
  command,
}: {
  channel: string
  lines: ChatLine[]
  command?: string
}) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    if (!command) return
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card text-foreground">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border bg-background px-4 py-2.5">
        <i className="fa-brands fa-twitch text-xl text-primary" />
        <span className="text-sub font-semibold text-foreground">{channel}</span>
        <span className="ml-auto text-label text-muted-foreground">聊天室</span>
      </div>

      {/* Messages */}
      <div className="flex flex-col gap-2 px-3 py-3">
        {lines.map((line, i) => {
          if (line.type === 'system') {
            return (
              <p key={i} className="text-label text-muted-foreground">
                {line.message}
              </p>
            )
          }
          return (
            <div key={i} className="flex flex-wrap items-center gap-0.5">
              <ChatBadgeIcon badge={line.badge} />
              <span className="text-sub font-bold" style={{ color: line.color }}>
                {line.username}
              </span>
              <span className="mx-1 text-sub text-muted-foreground">:</span>
              <span className="text-sub text-foreground">{line.message}</span>
            </div>
          )
        })}
      </div>

      {/* Input */}
      <div className="border-t border-border px-3 py-2.5">
        <div className="flex items-center gap-3 rounded bg-muted px-3 py-2">
          <i className="fa-regular fa-face-smile text-xl text-muted-foreground" />
          {command ? (
            <>
              <code className="flex-1 select-text font-mono text-label text-foreground">
                {command}
              </code>
              <button
                onClick={handleCopy}
                className="shrink-0 text-muted-foreground transition-colors hover:text-foreground"
                title="複製"
              >
                <i
                  className={`text-lg ${copied ? 'fa-solid fa-check text-status-success' : 'fa-regular fa-copy'}`}
                />
              </button>
            </>
          ) : (
            <>
              <span className="flex-1 text-label text-muted-foreground">
                在 {channel} 的聊天室發言…
              </span>
              <i className="fa-regular fa-paper-plane text-xl text-muted-foreground" />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

const MOD_CHAT_PREVIEW: ChatLine[] = [
  {
    type: 'message',
    badge: 'broadcaster',
    username: '你的頻道',
    color: '#ff4500',
    message: '/mod niibot_',
  },
  { type: 'system', message: '你的頻道 已賦予 niibot_ 的 Mod 優先權。' },
  {
    type: 'message',
    badge: 'mod',
    username: 'niibot_',
    color: '#00e676',
    message: '帽子叔叔正在巡邏...',
  },
]

const MOD_METHODS = [
  {
    icon: 'fa-solid fa-user',
    title: '從觀眾名單設定',
    desc: '點擊聊天室中機器人帳號名稱 → 展開用戶卡片 → 點擊「給予 Mod」按鈕',
  },
  {
    icon: 'fa-solid fa-gear',
    title: '從 Twitch 後台設定',
    desc: '前往 Twitch 後台 → 社群 → 角色管理 → 搜尋「泥爸」→ 設定為管理員（Moderator）',
  },
]

const NEXT_STEPS = [
  {
    icon: 'fa-solid fa-terminal',
    title: '建立第一個指令',
    desc: '新增觀眾可在聊天室呼叫的指令，可設定使用間隔與開放對象。',
    href: '/commands',
    badge: null,
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '設定事件自動回應',
    desc: '有人追蹤、訂閱或突襲時，自動發出你設定好的訊息。',
    href: '/events',
    badge: null,
  },
  {
    icon: 'fa-solid fa-clock',
    title: '新增定時訊息',
    desc: '定時廣播頻道資訊或活動公告，沒人聊天時不打擾。',
    href: '/timers',
    badge: null,
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '啟用遊戲排隊系統',
    desc: '管理觀眾排隊上下車，隊伍狀況同步顯示在直播畫面上。',
    href: '/modules/game-queue',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-film',
    title: '啟用影片排隊系統',
    desc: '觀眾投票想看的 YouTube 影片，自動排隊依序播放。',
    href: '/modules/video-queue',
    badge: 'OBS',
  },
]

export default function GetStarted() {
  useDocumentTitle('Get Started')

  return (
    <PageMain className="select-none">
      <PageHeader
        title="Get Started"
        description="授予機器人管理員身份，Niibot 就能在你的頻道正常運作。"
      />

      <SlideUp inView>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-3 text-card-title">
              <Icon
                icon="fa-solid fa-shield-halved"
                size="md"
                wrapperClassName="text-status-warning"
              />
              讓機器人成為聊天室管理員
            </CardTitle>
            <p className="text-sub text-muted-foreground">
              機器人需要 Mod 才能在你的頻道發言。透過右上角 <strong>Niibot</strong>{' '}
              選單一鍵授予，或使用下列方式手動設定。
            </p>
          </CardHeader>

          <CardContent>
            <div className="grid items-start gap-card lg:grid-cols-2">
              {/* Left: methods + notice */}
              <div className="flex flex-col gap-card">
                <div className="grid gap-element sm:grid-cols-2 lg:grid-cols-1">
                  {MOD_METHODS.map(method => (
                    <div key={method.title} className="flex gap-3 rounded-lg border bg-card p-page">
                      <Icon
                        icon={method.icon}
                        size="md"
                        wrapperClassName="mt-0.5 text-muted-foreground"
                      />
                      <div className="flex flex-col gap-element">
                        <p className="text-label font-medium">{method.title}</p>
                        <p className="text-label leading-relaxed text-muted-foreground">
                          {method.desc}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>

                <WarningBanner>
                  /mod 指令需由頻道主（Broadcaster）或頻道內的主要 Mod 執行。
                </WarningBanner>
              </div>

              <TwitchChatMockup
                channel="你的頻道"
                lines={MOD_CHAT_PREVIEW}
                command="/mod niibot_"
              />
            </div>
          </CardContent>
        </Card>
      </SlideUp>

      <section className="flex flex-col gap-section">
        <SlideUpSm inView delay={0.05}>
          <h2 className="text-section-title font-semibold">設定完成後，接著做什麼？</h2>
        </SlideUpSm>

        <Stagger inView className="grid gap-section sm:grid-cols-2 lg:grid-cols-3">
          {NEXT_STEPS.map(item => (
            <StaggerItem key={item.title}>
              <Link to={item.href} className="group">
                <Card className="h-full py-section transition-colors hover:border-primary/50 hover:bg-accent/30">
                  <CardContent className="flex flex-col gap-element">
                    <div className="flex items-center gap-2">
                      <Icon icon={item.icon} size="md" wrapperClassName="text-primary" />
                      <span className="text-sub font-semibold group-hover:text-primary">
                        {item.title}
                      </span>
                      {item.badge && (
                        <Badge variant="secondary" className="ml-auto text-label">
                          {item.badge}
                        </Badge>
                      )}
                    </div>
                    <p className="text-label leading-relaxed text-muted-foreground">{item.desc}</p>
                  </CardContent>
                </Card>
              </Link>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      <DiscordHelpBanner />
    </PageMain>
  )
}
