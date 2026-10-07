import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { motion, useReducedMotion } from 'motion/react'

import { BOT_USERNAME } from '@/api/config'
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
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useGrantMod } from '@/hooks/useGrantMod'
import { useOnboardingStatus } from '@/hooks/useOnboardingStatus'
import { copyToClipboard } from '@/lib/clipboard'
import { MANUAL_MOD_HASH } from '@/lib/mod-prompt'
import { countCompleted, type OnboardingStatus } from '@/lib/onboarding-status'

const MOD_COMMAND = `/mod ${BOT_USERNAME}`

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
    </div>
  )
}

const MOD_CHAT_PREVIEW: ChatLine[] = [
  { type: 'message', roles: ['broadcaster'], username: '你的頻道', message: MOD_COMMAND },
  { type: 'system', message: `你的頻道 已賦予 ${BOT_USERNAME} 的 Mod 優先權。` },
  {
    type: 'message',
    roles: ['moderator', 'bot'],
    username: BOT_USERNAME,
    message: '帽子叔叔正在巡邏...',
  },
]

const OTHER_MOD_METHODS = [
  { icon: 'fa-solid fa-user', text: `聊天室 → 觀眾名單 → 點 ${BOT_USERNAME} → 給予 Mod` },
  {
    icon: 'fa-solid fa-gear',
    text: `創作者儀表板 → 社群 → 角色管理員 → 新增 → 搜尋 ${BOT_USERNAME} → 勾選 Moderator`,
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
    desc: '自訂指令、冷卻與開放對象。',
    href: '/commands',
    doneKey: 'commandsDone',
  },
  {
    icon: 'fa-solid fa-bolt',
    title: '事件回應',
    desc: '追蹤、訂閱、突襲時自動回應。',
    href: '/events',
    doneKey: 'eventsDone',
  },
  {
    icon: 'fa-solid fa-clock',
    title: '定時訊息',
    desc: '定時發送頻道公告。',
    href: '/timers',
    doneKey: 'timersDone',
  },
  {
    icon: 'fa-solid fa-chart-mixed',
    title: '數據分析',
    desc: '觀眾互動紀錄與統計。',
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
    desc: '觀眾點播影片，自動播到直播畫面。',
    href: '/modules/video-queue',
    obs: true,
  },
  {
    icon: 'fa-solid fa-gamepad',
    title: '遊戲排隊',
    desc: '觀眾用指令排隊，即時同步畫面。',
    href: '/modules/game-queue',
    obs: true,
  },
  {
    icon: 'fa-solid fa-robot',
    title: 'AI 助理',
    desc: '讓機器人回答觀眾問題。',
    href: '/modules/ai',
  },
  {
    icon: 'fa-solid fa-crosshairs',
    title: '準星收藏',
    desc: '展示準星設定，觀眾一鍵複製。',
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

  // Arriving from the Overview prompt's "手動設定" opens the manual steps.
  const { hash } = useLocation()
  const fromManualLink = hash === `#${MANUAL_MOD_HASH}`
  const [manualOpen, setManualOpen] = useState(fromManualLink)
  useEffect(() => {
    if (!fromManualLink) return
    requestAnimationFrame(() =>
      document.getElementById(MANUAL_MOD_HASH)?.scrollIntoView({ block: 'center' })
    )
  }, [fromManualLink])

  return (
    <PageMain className="select-none">
      <PageHeader title="Get Started" description="讓 Niibot 成為管理員，就能開始使用。" />

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
                  {!modDone && (
                    <p className="text-sub text-muted-foreground">
                      需要 Mod 才能在頻道發言與執行指令。
                    </p>
                  )}
                </CardHeader>

                {!modDone && (
                  <CardContent className="flex flex-col gap-section">
                    <Button onClick={grantMod} disabled={granting} className="w-full">
                      {granting ? (
                        <Spinner className="mr-1.5" />
                      ) : (
                        <Icon icon="fa-solid fa-shield-halved" wrapperClassName="mr-1.5 size-3" />
                      )}
                      {granting ? '授予中…' : '一鍵授予 Mod'}
                    </Button>

                    <Collapsible
                      id={MANUAL_MOD_HASH}
                      open={manualOpen}
                      onOpenChange={setManualOpen}
                      className="rounded-lg border"
                    >
                      <CollapsibleTrigger className="group flex w-full items-center justify-between gap-element p-page text-sub font-medium">
                        <span>或手動設定</span>
                        <Icon
                          icon="fa-solid fa-chevron-down"
                          size="xs"
                          wrapperClassName="text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                        />
                      </CollapsibleTrigger>
                      <CollapsibleContent className="flex flex-col gap-card border-t p-page">
                        <div className="flex flex-col gap-element">
                          <p className="text-sub font-medium">聊天室指令</p>
                          <div className="flex items-center gap-element rounded-md bg-muted py-1 pl-3 pr-1">
                            <code className="flex-1 select-text font-mono text-sub">
                              {MOD_COMMAND}
                            </code>
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label="複製指令"
                              onClick={() => copyToClipboard(MOD_COMMAND, '已複製指令')}
                            >
                              <Icon icon="fa-solid fa-copy" size="xs" />
                            </Button>
                          </div>
                          <p className="text-label leading-relaxed text-muted-foreground">
                            在你自己頻道的聊天室送出，需由頻道主或主要 Mod
                            執行。成功後會出現系統訊息，機器人名稱旁多出 Mod 徽章：
                          </p>
                          <TwitchChatMockup channel="你的頻道" lines={MOD_CHAT_PREVIEW} />
                        </div>

                        <div className="flex flex-col gap-section border-t pt-card">
                          <p className="text-sub font-medium">其他方式</p>
                          {OTHER_MOD_METHODS.map(method => (
                            <div key={method.icon} className="flex items-start gap-3">
                              <Icon
                                icon={method.icon}
                                size="sm"
                                wrapperClassName="mt-0.5 shrink-0 text-muted-foreground"
                              />
                              <p className="select-text text-sub leading-relaxed">{method.text}</p>
                            </div>
                          ))}
                        </div>
                      </CollapsibleContent>
                    </Collapsible>
                  </CardContent>
                )}
              </Card>
            </SlideUp>
          </div>
        </div>
      </div>
    </PageMain>
  )
}
