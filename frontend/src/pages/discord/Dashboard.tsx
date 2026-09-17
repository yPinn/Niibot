import { DiscordHelpBanner } from '@/components/DiscordHelpBanner'
import { FeatureCard } from '@/components/FeatureCard'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, SlideUp, Stagger, StaggerItem } from '@/components/primitives'
import { Button, Card, CardContent } from '@/components/ui'
import { WarningBanner } from '@/components/WarningBanner'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const FEATURES = [
  {
    icon: 'fa-solid fa-share-nodes',
    title: '社群連結預覽',
    desc: '有人分享連結，Bot 自動顯示預覽圖卡，省去手動整理的麻煩。',
    tags: ['Instagram', 'Bilibili', 'TikTok', 'Threads', 'Twitch'],
  },
  {
    icon: 'fa-solid fa-scroll',
    title: '伺服器事件日誌',
    desc: '誰刪了訊息、誰的身份被調整，通通自動記錄到你指定的頻道。用 /setlog 設定一次就好。',
    tags: [],
  },
  {
    icon: 'fa-solid fa-cake-candles',
    title: '生日追蹤',
    desc: '成員自己登錄生日，Bot 記住後在當天自動送出祝賀，不需要你手動提醒。',
    tags: [],
  },
  {
    icon: 'fa-solid fa-gift',
    title: '抽獎系統',
    desc: '建立抽獎活動並設定參加條件，時間到自動抽出得獎者並公告。',
    tags: [],
  },
  {
    icon: 'fa-solid fa-stars',
    title: '占卜 & 戰棋',
    desc: '每日運勢、每日塔羅、TFT 當季排行門檻查詢與玩家段位搜尋。',
    tags: [],
  },
  {
    icon: 'fa-solid fa-robot',
    title: 'AI 對話',
    desc: '直接在頻道輸入問題，AI 即時回覆，不需切換到其他 App。',
    tags: [],
  },
]

const COMMANDS = [
  { cmd: '/bday menu', desc: '登錄、查詢或訂閱成員生日通知' },
  { cmd: '/giveaway', desc: '建立與管理抽獎活動' },
  { cmd: '/fortune', desc: '今日運勢' },
  { cmd: '/tarot', desc: '依主題抽取每日塔羅' },
  { cmd: '/tft [名稱#TAG]', desc: '查詢 TFT 當季排行門檻，或輸入玩家名稱查段位' },
  { cmd: '/ai <問題>', desc: '向 AI 提問' },
  { cmd: '/eat', desc: '隨機推薦今天吃什麼' },
]

const ADMIN_COMMANDS = [
  { cmd: '/setlog', desc: '指定要記錄伺服器動態的頻道' },
  { cmd: '/clear', desc: '一次清除多則訊息' },
  { cmd: '/kick /ban /mute', desc: '踢出、封鎖或禁言成員' },
]

const INVITE_URL = import.meta.env.VITE_DISCORD_BOT_INVITE_URL

export default function DiscordDashboard() {
  useDocumentTitle('Discord Bot')

  return (
    <PageMain className="select-none">
      <PageHeader
        title="Discord Bot"
        description="加入伺服器後即可使用，社群連結預覽、事件日誌等功能自動運行，無需額外設定。"
      />

      {/* Invite CTA */}
      <SlideUp>
        <div className="flex flex-col gap-section rounded-2xl border border-discord/20 bg-discord/5 p-page-lg sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-section">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl bg-discord/10">
              <Icon icon="fa-brands fa-discord" size="xl" wrapperClassName="text-discord" />
            </div>
            <div>
              <p className="text-card-title font-semibold">邀請 Bot 至您的伺服器</p>
              <p className="mt-0.5 text-sub text-muted-foreground">
                一鍵加入，功能立即可用，無需複雜設定。
              </p>
            </div>
          </div>
          {INVITE_URL ? (
            <Button asChild className="shrink-0 bg-discord hover:bg-discord/90">
              <a href={INVITE_URL} target="_blank" rel="noreferrer">
                <Icon icon="fa-solid fa-plus" size="sm" />
                邀請 Bot
              </a>
            </Button>
          ) : (
            <span className="shrink-0 rounded-lg border border-dashed border-discord/40 px-page py-2.5 text-sub text-muted-foreground">
              邀請連結設定中
            </span>
          )}
        </div>
      </SlideUp>

      <section className="flex flex-col gap-section">
        <h2 className="text-section-title font-semibold">功能介紹</h2>
        <Stagger inView className="grid gap-section sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <StaggerItem key={f.title} className="h-full">
              <FeatureCard
                icon={f.icon}
                title={f.title}
                description={f.desc}
                tags={f.tags}
                iconClassName="text-discord"
              />
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      <SlideUp inView delay={0.05}>
        <section className="flex flex-col gap-section">
          <h2 className="text-section-title font-semibold">常用指令</h2>
          <Card>
            <CardContent className="p-0">
              <div className="divide-y">
                {COMMANDS.map(({ cmd, desc }) => (
                  <div key={cmd} className="flex items-baseline gap-section px-page py-2">
                    <code className="w-44 shrink-0 font-mono text-sub font-semibold text-primary select-text">
                      {cmd}
                    </code>
                    <span className="text-sub text-muted-foreground">{desc}</span>
                  </div>
                ))}
              </div>
              <div className="border-t bg-muted/30 px-page py-1.5">
                <span className="flex items-center gap-1.5 text-label font-medium text-muted-foreground">
                  <Icon icon="fa-solid fa-shield-halved" size="xs" />
                  需要管理員權限
                </span>
              </div>
              <div className="divide-y">
                {ADMIN_COMMANDS.map(({ cmd, desc }) => (
                  <div key={cmd} className="flex items-baseline gap-section px-page py-2">
                    <code className="w-44 shrink-0 font-mono text-sub font-semibold text-primary select-text">
                      {cmd}
                    </code>
                    <span className="text-sub text-muted-foreground">{desc}</span>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </section>
      </SlideUp>

      <SlideUp inView delay={0.1}>
        <WarningBanner>
          <strong>伺服器事件日誌</strong>需要管理員先在頻道內執行一次{' '}
          <code className="font-mono font-semibold">/setlog</code>{' '}
          指定要記錄的頻道，之後就全自動。其他功能 Bot 加入後即可直接使用。
        </WarningBanner>
      </SlideUp>

      <SlideUp inView delay={0.15}>
        <DiscordHelpBanner />
      </SlideUp>
    </PageMain>
  )
}
