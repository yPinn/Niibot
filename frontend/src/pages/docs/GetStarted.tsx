import type { CSSProperties } from 'react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'

import { getBotModStatus, grantBotMod } from '@/api/channels'
import { PageHeader } from '@/components/PageHeader'
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Icon } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ─── Copy Button ─────────────────────────────────────────────────────────────

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

// ─── Twitch Chat Mockup ───────────────────────────────────────────────────────

type ChatBadge = 'broadcaster' | 'mod' | null

type ChatLine =
  | { type: 'message'; badge: ChatBadge; username: string; color: string; message: string }
  | { type: 'system'; message: string }

// Twitch badges are 18×18px squares with ~3px corner radius
function ChatBadgeIcon({ badge }: { badge: ChatBadge }) {
  const base: CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '18px',
    height: '18px',
    borderRadius: '3px',
    marginRight: '2px',
    flexShrink: 0,
    verticalAlign: 'middle',
  }
  if (badge === 'broadcaster') {
    return (
      <span style={{ ...base, background: '#e91916' }}>
        <i className="fa-solid fa-video text-white" style={{ fontSize: '8px' }} />
      </span>
    )
  }
  if (badge === 'mod') {
    return (
      <span style={{ ...base, background: '#00ad03' }}>
        <i className="fa-solid fa-gavel text-white" style={{ fontSize: '8px' }} />
      </span>
    )
  }
  return null
}

function TwitchChatMockup({ channel, lines }: { channel: string; lines: ChatLine[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-zinc-700 bg-[#18181b] text-white">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-zinc-700 bg-[#0e0e10] px-3 py-2">
        <i className="fa-brands fa-twitch text-label text-purple-400" />
        <span className="text-label font-semibold text-zinc-200">{channel}</span>
        <span className="ml-auto text-label text-zinc-500">聊天室</span>
      </div>

      {/* Messages */}
      <div className="flex flex-col p-3" style={{ gap: '2px' }}>
        {lines.map((line, i) => {
          if (line.type === 'system') {
            // Twitch system messages: plain light gray, no icon, no italic
            return (
              <p key={i} className="py-0.5 text-label" style={{ color: '#adadb8' }}>
                {line.message}
              </p>
            )
          }
          return (
            <div key={i} className="flex items-baseline" style={{ gap: '1px' }}>
              <ChatBadgeIcon badge={line.badge} />
              <span className="text-label font-bold" style={{ color: line.color }}>
                {line.username}
              </span>
              <span className="text-label" style={{ color: '#adadb8', margin: '0 2px' }}>
                :
              </span>
              <span className="text-label" style={{ color: '#efeff1' }}>
                {line.message}
              </span>
            </div>
          )
        })}
      </div>

      {/* Input bar */}
      <div className="border-t border-zinc-700 px-3 py-2">
        <div className="flex items-center gap-2 rounded bg-zinc-800 px-2 py-1.5">
          <span className="text-label flex-1 text-zinc-500">在 {channel} 的聊天室發言…</span>
          <i className="fa-regular fa-paper-plane text-label text-zinc-600" />
        </div>
      </div>
    </div>
  )
}

// ─── Setup Action ─────────────────────────────────────────────────────────────

const MOD_DETAILS = [
  { icon: 'fa-brands fa-twitch', text: '開啟 Twitch 並進入你的直播頻道聊天室' },
  { icon: 'fa-solid fa-terminal', text: '在聊天室輸入以下指令並送出' },
  {
    icon: 'fa-solid fa-user-shield',
    text: '看到通知「已賦予 niibot_ 的 Mod 優先權」即代表設定成功',
  },
]

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
    message: '感謝 mod！我會好好守護這個聊天室的 ✓',
  },
]

// ─── Next Steps ───────────────────────────────────────────────────────────────

const ALT_MOD_METHODS = [
  {
    icon: 'fa-solid fa-user',
    title: '從觀眾名單設定',
    desc: '點擊聊天室中機器人帳號名稱 → 展開用戶卡片 → 點擊「給予 Mod」按鈕',
  },
  {
    icon: 'fa-solid fa-gear',
    title: '從 Twitch 後台設定',
    desc: '前往 Twitch 後台 → 社群 → 角色管理 → 搜尋「泥爸」→ 設定為主持人（Moderator）',
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

// ─── Component ────────────────────────────────────────────────────────────────

export default function GetStarted() {
  useDocumentTitle('快速上手 — Niibot')

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
        toast.info('Niibot 已經是主持人了')
      } else if (res.granted) {
        setIsMod(true)
        toast.success('主持人授予成功')
      }
    } catch {
      toast.error('授予失敗，請稍後再試')
    } finally {
      setGranting(false)
    }
  }, [])

  return (
    <main className="flex flex-1 flex-col gap-card p-page lg:p-page-lg select-none">
      <PageHeader
        title="快速上手"
        description="完成 Mod 授權設定，Niibot 就能在你的頻道正常運作。"
      />

      {/* ── Setup Action ── */}
      <section className="flex flex-col gap-section">
        <h2 className="text-section-title font-semibold">設定步驟</h2>

        <Card>
          <CardHeader>
            <div className="flex items-start justify-between gap-3">
              <CardTitle className="flex items-center gap-3 text-card-title">
                <Icon
                  icon="fa-solid fa-shield-halved"
                  wrapperClassName="size-4 shrink-0 text-amber-500"
                />
                讓機器人成為聊天室主持人
              </CardTitle>
              {isMod === true && (
                <Badge className="shrink-0 bg-green-600 text-white hover:bg-green-600">
                  <Icon icon="fa-solid fa-check" wrapperClassName="mr-1 size-3" />
                  已設定
                </Badge>
              )}
            </div>
            <p className="text-sub text-muted-foreground">
              機器人需要主持人（Mod）身份才能在你的頻道正常發言與執行指令。
            </p>
          </CardHeader>

          <CardContent>
            <div className="grid items-start gap-card lg:grid-cols-2">
              {/* ── Left: step list + command + alt methods ── */}
              <div className="flex flex-col gap-card">
                {/* Detail list */}
                <ol className="flex flex-col gap-element">
                  {MOD_DETAILS.map((d, i) => (
                    <li key={i} className="flex items-start gap-2">
                      <Icon
                        icon={d.icon}
                        wrapperClassName="size-4 shrink-0 mt-0.5 text-muted-foreground"
                      />
                      <span className="text-sub text-muted-foreground">{d.text}</span>
                    </li>
                  ))}
                </ol>

                {/* Command block */}
                <div className="flex flex-col gap-element">
                  <div className="flex items-center gap-3 rounded-lg border bg-muted/50 px-page py-3">
                    <Icon
                      icon="fa-solid fa-terminal"
                      wrapperClassName="size-4 shrink-0 text-muted-foreground"
                    />
                    <code className="font-mono text-content font-semibold tracking-wide select-text">
                      /mod niibot_
                    </code>
                    <CopyButton text="/mod niibot_" />
                  </div>

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={handleGrantMod}
                    disabled={granting || isMod === true}
                    className="w-full"
                  >
                    {granting ? (
                      <>
                        <Icon icon="fa-solid fa-spinner fa-spin" wrapperClassName="mr-2 size-3" />
                        授予中…
                      </>
                    ) : isMod === true ? (
                      <>
                        <Icon
                          icon="fa-solid fa-check"
                          wrapperClassName="mr-2 size-3 text-green-500"
                        />
                        已授予主持人
                      </>
                    ) : (
                      <>
                        <Icon icon="fa-solid fa-user-shield" wrapperClassName="mr-2 size-3" />
                        一鍵授予主持人
                      </>
                    )}
                  </Button>

                  <p className="text-label text-muted-foreground">或選擇以下任一方式：</p>

                  <div className="grid gap-element sm:grid-cols-2 lg:grid-cols-1">
                    {ALT_MOD_METHODS.map(method => (
                      <div
                        key={method.title}
                        className="flex gap-3 rounded-lg border bg-card p-page"
                      >
                        <Icon
                          icon={method.icon}
                          wrapperClassName="size-4 shrink-0 mt-0.5 text-muted-foreground"
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
              </div>

              {/* ── Right: Twitch chat preview + warning ── */}
              <div className="flex flex-col gap-card">
                <TwitchChatMockup channel="你的頻道" lines={MOD_CHAT_PREVIEW} />

                {/* Warning note */}
                <div className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-page py-3 dark:border-amber-900/50 dark:bg-amber-950/30">
                  <Icon
                    icon="fa-solid fa-triangle-exclamation"
                    wrapperClassName="size-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-500"
                  />
                  <p className="text-label leading-relaxed text-amber-800 dark:text-amber-400">
                    /mod 指令只有頻道主（Broadcaster）才能執行，請確認你是以主播帳號登入 Twitch。
                  </p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </section>

      {/* ── Next Steps ── */}
      <section className="flex flex-col gap-section">
        <div className="flex flex-col gap-element">
          <h2 className="text-section-title font-semibold">設定完成後，接著做什麼？</h2>
          <p className="text-sub text-muted-foreground">從這些功能開始，讓 Niibot 發揮最大價值。</p>
        </div>

        <div className="grid gap-card sm:grid-cols-2 lg:grid-cols-3">
          {NEXT_STEPS.map(item => (
            <Link key={item.title} to={item.href} className="group">
              <Card className="h-full transition-colors hover:border-primary/50 hover:bg-accent/30">
                <CardContent className="flex flex-col gap-element">
                  <div className="flex items-center gap-2">
                    <Icon icon={item.icon} wrapperClassName="size-4 shrink-0 text-primary" />
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

      {/* ── Help footer ── */}
      <div className="flex items-center gap-3 rounded-xl border bg-muted/30 px-page py-3">
        <Icon icon="fa-brands fa-discord" wrapperClassName="size-5 shrink-0 text-blue-500" />
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
    </main>
  )
}
