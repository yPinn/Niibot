import type { CSSProperties } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { getBotModStatus, grantBotMod } from '@/api/channels'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <button
      onClick={handleCopy}
      className="ml-auto shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
      title="複製"
    >
      <i
        className={`text-label ${copied ? 'fa-solid fa-check text-green-500' : 'fa-regular fa-copy'}`}
      />
    </button>
  )
}

type ChatBadge = 'broadcaster' | 'mod' | null

type ChatLine =
  | { type: 'message'; badge: ChatBadge; username: string; color: string; message: string }
  | { type: 'system'; message: string }

// iOS inline badge: 20pt container, ~55% fill icon (11pt)
function ChatBadgeIcon({ badge }: { badge: ChatBadge }) {
  const base: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '20px',
    height: '20px',
    borderRadius: '4px',
    marginRight: '4px',
    flexShrink: 0,
    verticalAlign: 'middle',
  }
  if (badge === 'broadcaster') {
    return (
      <span style={{ ...base, background: '#e91916' }}>
        <i className="fa-solid fa-video text-white" style={{ fontSize: '11px' }} />
      </span>
    )
  }
  if (badge === 'mod') {
    return (
      <span style={{ ...base, background: '#00ad03' }}>
        <i className="fa-solid fa-gavel text-white" style={{ fontSize: '11px' }} />
      </span>
    )
  }
  return null
}

function TwitchChatMockup({ channel, lines }: { channel: string; lines: ChatLine[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-[#18181b] text-white">
      {/* Header — nav bar icon: 22pt (iOS HIG) */}
      <div className="flex items-center gap-2 border-b border-zinc-700 bg-[#0e0e10] px-4 py-2.5">
        <i className="fa-brands fa-twitch text-purple-400" style={{ fontSize: '22px' }} />
        <span className="font-semibold text-zinc-200" style={{ fontSize: '15px' }}>
          {channel}
        </span>
        <span className="ml-auto text-zinc-500" style={{ fontSize: '13px' }}>
          聊天室
        </span>
      </div>

      {/* Messages — body 15pt, footnote 13pt (iOS HIG) */}
      <div className="flex flex-col px-3 py-3" style={{ gap: '8px' }}>
        {lines.map((line, i) => {
          if (line.type === 'system') {
            return (
              <p key={i} style={{ fontSize: '13px', color: '#adadb8' }}>
                {line.message}
              </p>
            )
          }
          return (
            <div key={i} className="flex items-center flex-wrap" style={{ gap: '2px' }}>
              <ChatBadgeIcon badge={line.badge} />
              <span className="font-bold" style={{ fontSize: '15px', color: line.color }}>
                {line.username}
              </span>
              <span style={{ fontSize: '15px', color: '#adadb8', margin: '0 3px' }}>:</span>
              <span style={{ fontSize: '15px', color: '#efeff1' }}>{line.message}</span>
            </div>
          )
        })}
      </div>

      {/* Input — toolbar icons: 22pt (iOS HIG) */}
      <div className="border-t border-zinc-700 px-3 py-2.5">
        <div className="flex items-center gap-3 rounded bg-zinc-800 px-3 py-2">
          <i className="fa-regular fa-face-smile text-zinc-500" style={{ fontSize: '22px' }} />
          <span className="flex-1 text-zinc-500" style={{ fontSize: '13px' }}>
            在 {channel} 的聊天室發言…
          </span>
          <i className="fa-regular fa-paper-plane text-zinc-500" style={{ fontSize: '22px' }} />
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

const ALT_MOD_METHODS = [
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

  const [isMod, setIsMod] = useState<boolean | null>(null)
  const [granting, setGranting] = useState(false)

  useEffect(() => {
    getBotModStatus().then(res => {
      if (res !== null) setIsMod(res.is_moderator)
    })
  }, [])

  const handleGrantMod = useCallback(async () => {
    setGranting(true)
    try {
      const res = await grantBotMod()
      if (res.already_mod) {
        setIsMod(true)
        toast.info('Niibot 已經是管理員了')
      } else if (res.granted) {
        setIsMod(true)
        toast.success('管理員授予成功')
      }
    } catch {
      toast.error('授予失敗，請稍後再試')
    } finally {
      setGranting(false)
    }
  }, [])

  return (
    <PageMain className="select-none">
      <PageHeader
        title="Get Started"
        description="授予機器人管理員身份，Niibot 就能在你的頻道正常運作。"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-3 text-card-title">
            <Icon icon="fa-solid fa-shield-halved" size="md" wrapperClassName="text-amber-500" />
            讓機器人成為聊天室管理員
          </CardTitle>
          <p className="text-sub text-muted-foreground">
            Mod 是 Twitch 頻道的管理員身份，機器人需要此身份才能在你的頻道正常發言與執行指令。
          </p>
        </CardHeader>

        <CardContent>
          <div className="grid items-start gap-card lg:grid-cols-2">
            {/* Left: primary CTA + manual fallback */}
            <div className="flex flex-col gap-card">
              {isMod === null ? (
                <div className="h-9 w-full animate-pulse rounded-md bg-muted" />
              ) : (
                <Button
                  type="button"
                  variant={isMod === true ? 'outline' : 'default'}
                  size="default"
                  onClick={handleGrantMod}
                  disabled={granting || isMod === true}
                  className="w-full"
                >
                  {granting ? (
                    <>
                      <Icon icon="fa-solid fa-spinner fa-spin" size="sm" />
                      授予中…
                    </>
                  ) : isMod === true ? (
                    <>
                      <Icon icon="fa-solid fa-check" size="sm" wrapperClassName="text-green-500" />
                      已是管理員
                    </>
                  ) : (
                    <>
                      <Icon icon="fa-solid fa-user-shield" size="sm" />
                      一鍵授予管理員
                    </>
                  )}
                </Button>
              )}

              <div className="flex items-center gap-3">
                <div className="flex-1 border-t" />
                <span className="text-label shrink-0 text-muted-foreground">或手動授予</span>
                <div className="flex-1 border-t" />
              </div>

              <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-page py-3">
                <Icon
                  icon="fa-solid fa-terminal"
                  size="md"
                  wrapperClassName="text-muted-foreground"
                />
                <code className="font-mono text-content font-semibold tracking-wide select-text">
                  /mod niibot_
                </code>
                <CopyButton text="/mod niibot_" />
              </div>

              <div className="grid gap-element sm:grid-cols-2 lg:grid-cols-1">
                {ALT_MOD_METHODS.map(method => (
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
            </div>

            {/* Right: mockup + notice */}
            <div className="flex flex-col gap-card">
              <TwitchChatMockup channel="你的頻道" lines={MOD_CHAT_PREVIEW} />

              <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-page py-3 dark:border-amber-900/50 dark:bg-amber-950/30">
                <Icon
                  icon="fa-solid fa-triangle-exclamation"
                  size="md"
                  wrapperClassName="mt-0.5 text-amber-600 dark:text-amber-500"
                />
                <p className="text-label leading-relaxed text-amber-800 dark:text-amber-400">
                  /mod 指令需由頻道主（Broadcaster）或頻道內的主要 Mod 執行。
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      <section className="flex flex-col gap-section">
        <div className="flex flex-col gap-element">
          <h2 className="text-section-title font-semibold">設定完成後，接著做什麼？</h2>
          <p className="text-sub text-muted-foreground">從這些功能開始，讓 Niibot 發揮最大價值。</p>
        </div>

        <div className="grid gap-section sm:grid-cols-2 lg:grid-cols-3">
          {NEXT_STEPS.map(item => (
            <Link key={item.title} to={item.href} className="group">
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
          ))}
        </div>
      </section>

      <div className="flex items-center gap-3 rounded-xl border bg-muted/30 px-page py-3">
        <Icon icon="fa-brands fa-discord" size="lg" wrapperClassName="text-blue-500" />
        <p className="text-sub">
          <span className="font-medium">遇到問題？</span>
          <span className="ml-1 text-muted-foreground">
            加入{' '}
            <a
              href="https://discord.gg/zhtUKMuzpY"
              target="_blank"
              rel="noreferrer"
              className="text-primary underline-offset-4 hover:underline"
            >
              Discord 社群
            </a>{' '}
            回報問題或提出建議。
          </span>
        </p>
      </div>
    </PageMain>
  )
}
