import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'

import { DiscordHelpBanner } from '@/components/DiscordHelpBanner'
import { FeatureCard } from '@/components/FeatureCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import {
  Icon,
  SlideUp,
  Spinner,
  Stagger,
  StaggerItem,
  TwitchBadgeGroup,
  type TwitchRole,
} from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useGrantMod } from '@/hooks/useGrantMod'
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

const LINE_DELAYS = [0, 600, 1100]

/** Types the three chat lines in once, then holds. No loop — this is a reference page. */
function TwitchChatMockup({ channel, lines }: { channel: string; lines: ChatLine[] }) {
  const reduceMotion = useReducedMotion()
  const [typed, setTyped] = useState(0)

  useEffect(() => {
    if (reduceMotion) return
    const timers = lines.map((_, i) => setTimeout(() => setTyped(i + 1), LINE_DELAYS[i] ?? 0))
    return () => timers.forEach(clearTimeout)
  }, [reduceMotion, lines])

  const visibleCount = reduceMotion ? lines.length : typed

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card text-foreground">
      <div className="flex items-center gap-element border-b border-border bg-background px-page py-2.5">
        <Icon icon="fa-brands fa-twitch" size="lg" wrapperClassName="text-primary" />
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
              key={i}
              initial={reduceMotion ? false : { opacity: 0, y: 6 }}
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
          <Icon
            icon="fa-regular fa-face-smile"
            size="lg"
            wrapperClassName="text-muted-foreground"
          />
          <code className="flex-1 select-text font-mono text-label text-foreground">
            /mod niibot_
          </code>
          <Icon
            icon="fa-regular fa-paper-plane"
            size="lg"
            wrapperClassName="text-muted-foreground"
          />
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
    desc: '點機器人帳號 → 用戶卡片 → 給予 Mod',
  },
  {
    icon: 'fa-solid fa-gear',
    title: '從 Twitch 後台設定',
    desc: '後台 → 社群 → 角色管理 → 搜尋帳號 → 設為 Moderator',
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
    desc: '新增觀眾可呼叫的指令，可設冷卻時間與開放對象，內建與完全自訂都支援。',
    href: '/commands',
    doneKey: 'commandsDone',
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '事件回應',
    desc: '追蹤、訂閱、突襲或贈禮時自動發出設定好的訊息，互動不漏接。',
    href: '/events',
    doneKey: 'eventsDone',
  },
  {
    icon: 'fa-solid fa-clock',
    title: '定時訊息',
    desc: '週期性自動發送頻道公告，靜止時段不觸發。',
    href: '/timers',
    doneKey: 'timersDone',
  },
  {
    icon: 'fa-solid fa-chart-mixed',
    title: '數據分析',
    desc: '查看觀眾互動紀錄與統計，並同步 Twitch 角色到觀眾資料庫。',
    href: '/analytics/insights',
  },
]

const MODULE_FEATURES: {
  icon: string
  title: string
  desc: string
  href: string
  obs?: boolean
}[] = [
  {
    icon: 'fa-solid fa-film',
    title: '影片排隊',
    desc: '觀眾點播影片排隊，自動播到直播畫面，支援 YouTube、Twitch、Bilibili。',
    href: '/modules/video-queue',
    obs: true,
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '遊戲排隊',
    desc: '觀眾用指令排隊，隊伍即時同步到直播畫面。',
    href: '/modules/game-queue',
    obs: true,
  },
  {
    icon: 'fa-solid fa-robot',
    title: 'AI 助理',
    desc: '串接 AI 讓機器人回答觀眾問題，人設可自訂。',
    href: '/modules/ai',
  },
  {
    icon: 'fa-solid fa-crosshairs',
    title: '準星收藏',
    desc: '收藏並展示準星設定，觀眾一鍵複製套用。',
    href: '/modules/crosshairs',
  },
]

export default function GetStarted() {
  useDocumentTitle('Get Started')
  const { loading: statusLoading, status } = useOnboardingStatus()
  const { completed, total } = countCompleted(status)

  const [justGranted, setJustGranted] = useState(false)
  const { granting, grantMod } = useGrantMod(() => setJustGranted(true))
  const modDone = status.modDone || justGranted

  return (
    <PageMain className="select-none">
      <PageHeader title="Get Started" description="把 Niibot 加進頻道，開始使用這些功能。" />

      <div className="grid gap-section lg:grid-cols-3 lg:items-start">
        <div className="order-last flex flex-col gap-section lg:order-first lg:col-span-2">
          <section className="flex flex-col gap-section">
            <div className="flex items-center gap-2">
              <h2 className="text-section-title font-semibold">核心功能</h2>
              {!statusLoading && total > 0 && (
                <Badge variant="outline" className="text-label border-primary/30 text-primary/70">
                  {completed}/{total} 已完成
                </Badge>
              )}
            </div>
            <Stagger inView className="grid gap-section sm:grid-cols-2">
              {CORE_FEATURES.map(item => (
                <StaggerItem key={item.title} className="h-full">
                  <FeatureCard
                    icon={item.icon}
                    title={item.title}
                    description={item.desc}
                    href={item.href}
                    done={item.doneKey && !statusLoading ? status[item.doneKey] : undefined}
                  />
                </StaggerItem>
              ))}
            </Stagger>
          </section>

          <section className="flex flex-col gap-section">
            <h2 className="text-section-title font-semibold">直播畫面模組</h2>
            <p className="text-sub text-muted-foreground">
              按需啟用的進階功能，標記 OBS 的可直接整合到直播畫面。
            </p>
            <Stagger inView className="grid gap-section sm:grid-cols-2">
              {MODULE_FEATURES.map(item => (
                <StaggerItem key={item.title} className="h-full">
                  <FeatureCard
                    icon={item.icon}
                    title={item.title}
                    description={item.desc}
                    href={item.href}
                    badge={item.obs ? 'OBS' : undefined}
                    accent={item.obs}
                  />
                </StaggerItem>
              ))}
            </Stagger>
          </section>

          <SlideUp inView delay={0.1}>
            <DiscordHelpBanner />
          </SlideUp>
        </div>

        <div className="order-first lg:order-last">
          <div className="lg:sticky lg:top-4">
            <SlideUp inView>
              <Card className="border-primary/30 bg-primary/2">
                <CardHeader>
                  <CardTitle className="flex items-center gap-3 text-card-title">
                    <Icon
                      icon="fa-solid fa-shield-halved"
                      size="md"
                      wrapperClassName="text-primary"
                    />
                    讓 Niibot 成為管理員
                    {!statusLoading && modDone && (
                      <Badge
                        variant="outline"
                        className="ml-auto shrink-0 text-label border-status-success/30 text-status-success"
                      >
                        已完成
                      </Badge>
                    )}
                  </CardTitle>
                  <p className="text-sub text-muted-foreground">
                    機器人需要 Mod 才能在你的頻道發言、執行指令與事件。
                  </p>
                </CardHeader>

                <CardContent className="flex flex-col gap-card">
                  {modDone ? (
                    <div className="flex items-center gap-element rounded-lg border border-status-success/30 bg-status-success/5 p-page text-sub">
                      <Icon
                        icon="fa-solid fa-circle-check"
                        size="md"
                        wrapperClassName="text-status-success"
                      />
                      Niibot 已經是這個頻道的管理員。
                    </div>
                  ) : (
                    <Button onClick={grantMod} disabled={granting} className="w-full">
                      {granting ? (
                        <Spinner className="mr-1.5" />
                      ) : (
                        <Icon icon="fa-solid fa-shield-halved" wrapperClassName="mr-1.5 size-3" />
                      )}
                      {granting ? '授予中…' : '一鍵授予 Mod'}
                    </Button>
                  )}

                  <Collapsible className="rounded-lg border">
                    <CollapsibleTrigger className="group flex w-full items-center justify-between gap-element p-page text-sub font-medium">
                      <span>或手動設定</span>
                      <Icon
                        icon="fa-solid fa-chevron-down"
                        size="xs"
                        wrapperClassName="text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                      />
                    </CollapsibleTrigger>
                    <CollapsibleContent className="flex flex-col gap-card border-t p-page">
                      {MOD_METHODS.map(method => (
                        <div key={method.title} className="flex gap-3">
                          <Icon
                            icon={method.icon}
                            size="md"
                            wrapperClassName="mt-0.5 shrink-0 text-muted-foreground"
                          />
                          <div className="flex flex-col gap-0.5">
                            <p className="text-sub font-medium">{method.title}</p>
                            <p className="text-sub leading-relaxed text-muted-foreground">
                              {method.desc}
                            </p>
                          </div>
                        </div>
                      ))}
                    </CollapsibleContent>
                  </Collapsible>

                  <TwitchChatMockup channel="你的頻道" lines={MOD_CHAT_PREVIEW} />

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
