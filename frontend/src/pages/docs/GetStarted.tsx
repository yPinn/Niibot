import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'motion/react'

import { DiscordHelpBanner } from '@/components/DiscordHelpBanner'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import {
  Icon,
  SlideUp,
  Stagger,
  StaggerItem,
  TwitchBadgeGroup,
  type TwitchRole,
} from '@/components/primitives'
import { Badge, Card, CardContent, CardHeader, CardTitle } from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOnboardingStatus } from '@/hooks/useOnboardingStatus'
import { countCompleted, type OnboardingStatus } from '@/lib/onboarding-status'

type ChatLine =
  | { type: 'message'; roles: TwitchRole[]; username: string; message: string }
  | { type: 'system'; message: string }

const ROLE_CSS_VAR: Partial<Record<TwitchRole, string>> = {
  broadcaster: 'var(--chat-role-broadcaster)',
  moderator: 'var(--chat-role-mod)',
  vip: 'var(--chat-role-vip)',
}

const ROLE_PRIORITY: TwitchRole[] = ['broadcaster', 'moderator', 'vip']

function getRoleColor(roles: TwitchRole[]): string {
  const dominant = ROLE_PRIORITY.find(r => roles.includes(r))
  return dominant
    ? (ROLE_CSS_VAR[dominant] ?? 'var(--chat-role-default)')
    : 'var(--chat-role-default)'
}

const LINE_DELAYS: [number, number, number] = [0, 600, 1100]
const LOOP_DURATION = 3800

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
  const [{ visibleCount, loopKey }, setAnim] = useState({ visibleCount: 0, loopKey: 0 })

  useEffect(() => {
    const timers = lines.map((_, i) =>
      setTimeout(() => setAnim(prev => ({ ...prev, visibleCount: i + 1 })), LINE_DELAYS[i] ?? 0)
    )
    const reset = setTimeout(
      () => setAnim(prev => ({ loopKey: prev.loopKey + 1, visibleCount: 0 })),
      LOOP_DURATION
    )
    return () => {
      timers.forEach(clearTimeout)
      clearTimeout(reset)
    }
  }, [loopKey, lines])

  function handleCopy() {
    if (!command) return
    navigator.clipboard.writeText(command).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card text-foreground">
      <div className="flex items-center gap-element border-b border-border bg-background px-page py-2.5">
        <i className="fa-brands fa-twitch text-section-title text-primary" />
        <span className="text-sub font-semibold text-foreground">{channel}</span>
        <span className="ml-auto text-label text-muted-foreground">聊天室</span>
      </div>

      <div className="flex h-28 flex-col justify-end gap-element overflow-hidden px-3 py-3">
        {lines.slice(0, visibleCount).map((line, i) => {
          const content =
            line.type === 'system' ? (
              <p className="text-label text-muted-foreground">{line.message}</p>
            ) : (
              <div className="flex flex-wrap items-center">
                {line.roles.length > 0 && (
                  <TwitchBadgeGroup badges={line.roles.map(role => ({ role }))} className="mr-1" />
                )}
                <span className="text-sub font-bold" style={{ color: getRoleColor(line.roles) }}>
                  {line.username}
                </span>
                <span className="text-sub text-muted-foreground opacity-55">{': '}</span>
                <span className="text-sub text-foreground">{line.message}</span>
              </div>
            )
          return (
            <motion.div
              key={`${loopKey}-${i}`}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
            >
              {content}
            </motion.div>
          )
        })}
      </div>

      <div className="border-t border-border px-3 py-2.5">
        <div className="flex items-center gap-3 rounded bg-muted px-3 py-2">
          <i className="fa-regular fa-face-smile text-section-title text-muted-foreground" />
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
                  className={`text-card-title ${copied ? 'fa-solid fa-check text-status-success' : 'fa-regular fa-copy'}`}
                />
              </button>
            </>
          ) : (
            <>
              <span className="flex-1 text-label text-muted-foreground">
                在 {channel} 的聊天室發言…
              </span>
              <i className="fa-regular fa-paper-plane text-section-title text-muted-foreground" />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

const MOD_CHAT_PREVIEW: ChatLine[] = [
  { type: 'message', roles: ['broadcaster'], username: '你的頻道', message: '/mod niibot_' },
  { type: 'system', message: '你的頻道 已賦予 niibot_ 的 Mod 優先權。' },
  {
    type: 'message',
    roles: ['moderator', 'bot'],
    username: 'niibot_',
    message: '帽子叔叔正在巡邏...',
  },
]

const MOD_METHODS = [
  {
    icon: 'fa-solid fa-user',
    title: '從觀眾名單設定',
    desc: '點擊機器人帳號 → 用戶卡片 → 給予 Mod',
  },
  {
    icon: 'fa-solid fa-gear',
    title: '從 Twitch 後台設定',
    desc: 'Twitch 後台 → 社群 → 角色管理 → 搜尋帳號 → 設為 Moderator',
  },
]

const CORE_FEATURES: {
  icon: string
  title: string
  desc: string
  href: string
  doneKey?: keyof OnboardingStatus
}[] = [
  {
    icon: 'fa-solid fa-terminal',
    title: '指令管理',
    desc: '新增觀眾可呼叫的指令，可設冷卻時間與開放對象，支援內建與完全自訂。',
    href: '/commands',
    doneKey: 'commandsDone',
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '事件回應',
    desc: '追蹤、訂閱、突襲或贈禮時，自動發出設定的訊息，互動不漏掉。',
    href: '/events',
    doneKey: 'eventsDone',
  },
  {
    icon: 'fa-solid fa-clock',
    title: '定時訊息',
    desc: '設定週期性廣播自動發送頻道公告，靜止時段不觸發。',
    href: '/timers',
    doneKey: 'timersDone',
  },
  {
    icon: 'fa-solid fa-chart-mixed',
    title: '數據分析',
    desc: '查看觀眾互動紀錄與統計，並同步 Twitch 角色至觀眾資料庫。',
    href: '/analytics/insights',
  },
]

const MODULE_FEATURES = [
  {
    icon: 'fa-solid fa-film',
    title: '影片排隊',
    desc: '觀眾投稿影片連結排隊，支援 YouTube、Bilibili、Twitch Clip。',
    href: '/modules/video-queue',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '遊戲排隊',
    desc: '觀眾指令排隊，隊伍即時同步至 OBS 畫面。',
    href: '/modules/game-queue',
    badge: 'OBS',
  },
  {
    icon: 'fa-solid fa-robot',
    title: 'AI 助理',
    desc: '串接 AI 讓機器人回答觀眾問題，可自訂人設。',
    href: '/modules/ai',
    badge: null,
  },
  {
    icon: 'fa-solid fa-crosshairs',
    title: '準星收藏',
    desc: '收藏展示準星設定，觀眾一鍵複製套用。',
    href: '/modules/crosshairs',
    badge: null,
  },
]

export default function GetStarted() {
  useDocumentTitle('Get Started')
  const { loading: statusLoading, status } = useOnboardingStatus()
  const { completed, total } = countCompleted(status)

  return (
    <PageMain className="select-none">
      <PageHeader
        title="Get Started"
        description="授予機器人管理員身份，Niibot 就能在你的頻道正常運作。"
      />

      <div className="grid gap-section lg:grid-cols-3 lg:items-start">
        <div className="order-last lg:order-first lg:col-span-2 flex flex-col gap-section">
          <SlideUp inView delay={0.05}>
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-card-title">
                  核心功能
                  {!statusLoading && total > 0 && (
                    <Badge
                      variant="outline"
                      className="text-label border-primary/30 text-primary/70"
                    >
                      {completed}/{total} 已完成
                    </Badge>
                  )}
                </CardTitle>
                <p className="text-sub text-muted-foreground">
                  授予 Mod 後，建議先熟悉這幾項核心功能。
                </p>
              </CardHeader>
              <CardContent>
                <Stagger inView className="flex flex-col divide-y divide-border">
                  {CORE_FEATURES.map((item, idx) => (
                    <StaggerItem key={item.title}>
                      <Link
                        to={item.href}
                        className="group flex items-start gap-section py-page transition-colors hover:text-primary"
                      >
                        <span className="mt-0.5 shrink-0 w-5 text-label font-mono text-primary/40 group-hover:text-primary/80 transition-colors tabular-nums">
                          {String(idx + 1).padStart(2, '0')}
                        </span>
                        <Icon
                          icon={item.icon}
                          size="md"
                          wrapperClassName="mt-0.5 shrink-0 text-primary/70 group-hover:text-primary transition-colors"
                        />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-1.5">
                            <p className="text-sub font-semibold group-hover:text-primary transition-colors">
                              {item.title}
                            </p>
                            {item.doneKey &&
                              !statusLoading &&
                              status[item.doneKey] !== null &&
                              (status[item.doneKey] ? (
                                <Icon
                                  icon="fa-solid fa-circle-check"
                                  size="xs"
                                  wrapperClassName="text-status-success"
                                />
                              ) : (
                                <Icon
                                  icon="fa-regular fa-circle"
                                  size="xs"
                                  wrapperClassName="text-muted-foreground/50"
                                />
                              ))}
                          </div>
                          <p className="text-label leading-relaxed text-muted-foreground mt-0.5">
                            {item.desc}
                          </p>
                        </div>
                        <Icon
                          icon="fa-solid fa-arrow-right"
                          className="mt-1 shrink-0 text-label text-muted-foreground/30 group-hover:text-primary/60 transition-colors"
                        />
                      </Link>
                    </StaggerItem>
                  ))}
                </Stagger>
              </CardContent>
            </Card>
          </SlideUp>

          <SlideUp inView delay={0.1}>
            <Card>
              <CardHeader>
                <CardTitle className="text-card-title">模組功能</CardTitle>
                <p className="text-sub text-muted-foreground">
                  按需啟用的進階功能，OBS 標記的模組可直接整合至直播畫面。
                </p>
              </CardHeader>
              <CardContent>
                <Stagger inView className="grid gap-card grid-cols-1 sm:grid-cols-2">
                  {MODULE_FEATURES.map(item => {
                    const isObs = !!item.badge
                    return (
                      <StaggerItem key={item.title}>
                        <Link to={item.href} className="group block h-full">
                          <div
                            className={`flex flex-col gap-element rounded-lg border p-page h-full transition-colors ${isObs ? 'bg-primary/5 border-primary/20 hover:bg-primary/10 hover:border-primary/40' : 'bg-muted/20 hover:bg-accent/20'}`}
                          >
                            <div className="flex items-center justify-between gap-element">
                              <div className="flex items-center gap-element">
                                <Icon
                                  icon={item.icon}
                                  size="md"
                                  wrapperClassName={
                                    isObs
                                      ? 'text-primary/70 group-hover:text-primary transition-colors'
                                      : 'text-muted-foreground'
                                  }
                                />
                                <p
                                  className={`text-sub font-semibold ${isObs ? 'group-hover:text-primary' : 'group-hover:text-foreground'} transition-colors`}
                                >
                                  {item.title}
                                </p>
                              </div>
                              {item.badge && (
                                <Badge
                                  variant="outline"
                                  className="shrink-0 text-label border-primary/30 text-primary/70"
                                >
                                  {item.badge}
                                </Badge>
                              )}
                            </div>
                            <p className="text-label leading-relaxed text-muted-foreground">
                              {item.desc}
                            </p>
                          </div>
                        </Link>
                      </StaggerItem>
                    )
                  })}
                </Stagger>
              </CardContent>
            </Card>
          </SlideUp>

          <DiscordHelpBanner />
        </div>

        <div className="order-first lg:order-last">
          <div className="lg:sticky lg:top-4">
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
                    {!statusLoading && status.modDone && (
                      <Badge
                        variant="outline"
                        className="ml-auto shrink-0 text-label border-status-success/30 text-status-success"
                      >
                        已完成
                      </Badge>
                    )}
                  </CardTitle>
                  <p className="text-sub text-muted-foreground">
                    機器人需要 Mod 才能發言。點選右上角 <strong>Niibot</strong>{' '}
                    選單一鍵授予，或手動設定。
                  </p>
                </CardHeader>

                <CardContent className="flex flex-col gap-card">
                  <div className="flex flex-col gap-element">
                    {MOD_METHODS.map(method => (
                      <div
                        key={method.title}
                        className="flex gap-3 rounded-lg border bg-card p-page"
                      >
                        <Icon
                          icon={method.icon}
                          size="md"
                          wrapperClassName="mt-0.5 text-muted-foreground"
                        />
                        <div className="flex flex-col gap-element">
                          <p className="text-sub font-medium">{method.title}</p>
                          <p className="text-label leading-relaxed text-muted-foreground">
                            {method.desc}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>

                  <TwitchChatMockup
                    channel="你的頻道"
                    lines={MOD_CHAT_PREVIEW}
                    command="/mod niibot_"
                  />

                  <WarningBanner>
                    /mod 指令需由頻道主（Broadcaster）或頻道內的主要 Mod 執行。
                  </WarningBanner>
                </CardContent>
              </Card>
            </SlideUp>
          </div>
        </div>
      </div>
    </PageMain>
  )
}
