import { PageHeader } from '@/components/PageHeader'
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  SlideUp,
  Stagger,
  StaggerItem,
} from '@/components/ui'
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
    desc: '每日運勢、塔羅牌占卜、TFT 當季排行門檻查詢與玩家段位搜尋。',
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
  { cmd: '/setlog', desc: '指定要記錄伺服器動態的頻道（需管理員）' },
  { cmd: '/bday menu', desc: '登錄、查詢或訂閱成員生日通知' },
  { cmd: '/giveaway', desc: '建立與管理抽獎活動' },
  { cmd: '/fortune', desc: '今日運勢（每人每日一次）' },
  { cmd: '/tarot', desc: '塔羅牌占卜' },
  { cmd: '/tft [名稱#TAG]', desc: '查詢 TFT 當季排行門檻，或輸入玩家名稱查段位' },
  { cmd: '/ai <問題>', desc: '向 AI 提問' },
  { cmd: '/eat', desc: '隨機推薦今天吃什麼' },
  { cmd: '/clear', desc: '一次清除多則訊息（需管理員）' },
  { cmd: '/kick /ban /mute', desc: '踢出、封鎖或禁言成員（需管理員）' },
]

export default function DiscordDashboard() {
  useDocumentTitle('Discord Bot — Niibot')

  return (
    <main className="flex flex-1 flex-col gap-card p-page lg:p-page-lg select-none">
      <SlideUp>
        <PageHeader
          title="Discord Bot"
          description="加入伺服器後即可使用，社群連結預覽、事件日誌等功能自動運行，無需額外設定。"
        />
      </SlideUp>

      {/* Features */}
      <section className="flex flex-col gap-section">
        <h2 className="text-section-title font-semibold">功能介紹</h2>
        <Stagger inView className="grid gap-card sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(f => (
            <StaggerItem key={f.title}>
              <Card className="h-full">
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-card-title">
                    <Icon icon={f.icon} wrapperClassName="size-4 shrink-0 text-[#5865F2]" />
                    {f.title}
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <p className="text-sub leading-relaxed text-muted-foreground">{f.desc}</p>
                  {f.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {f.tags.map(tag => (
                        <Badge key={tag} variant="secondary" className="text-label">
                          {tag}
                        </Badge>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </StaggerItem>
          ))}
        </Stagger>
      </section>

      {/* Commands */}
      <SlideUp inView delay={0.05}>
        <section className="flex flex-col gap-section">
          <h2 className="text-section-title font-semibold">常用指令</h2>
          <Card>
            <CardContent className="p-0">
              <div className="divide-y">
                {COMMANDS.map(({ cmd, desc }) => (
                  <div key={cmd} className="flex items-baseline gap-4 px-page py-3">
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

      {/* Setup note */}
      <SlideUp inView delay={0.1}>
        <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 px-page py-3 dark:border-amber-900/50 dark:bg-amber-950/30">
          <Icon
            icon="fa-solid fa-triangle-exclamation"
            wrapperClassName="size-4 shrink-0 mt-0.5 text-amber-600 dark:text-amber-500"
          />
          <p className="text-sub leading-relaxed text-amber-800 dark:text-amber-400">
            <strong>伺服器事件日誌</strong>需要管理員先在頻道內執行一次{' '}
            <code className="font-mono font-semibold">/setlog</code>{' '}
            指定要記錄的頻道，之後就全自動。其他功能 Bot 加入後即可直接使用。
          </p>
        </div>
      </SlideUp>

      {/* Help */}
      <SlideUp inView delay={0.1}>
        <div className="flex items-center gap-3 rounded-xl border bg-muted/30 px-page py-3">
          <Icon icon="fa-brands fa-discord" wrapperClassName="size-5 shrink-0 text-[#5865F2]" />
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
      </SlideUp>
    </main>
  )
}
