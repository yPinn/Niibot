import { Link } from 'react-router-dom'

import { Icon } from '@/components/primitives'
import { Button } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const EFFECTIVE_DATE = '2026 年 4 月 23 日'
const SERVICE_NAME = 'Niibot'
const CONTACT_DISCORD = import.meta.env.VITE_DISCORD_INVITE_URL

function Section({
  id,
  title,
  children,
}: {
  id: string
  title: string
  children: React.ReactNode
}) {
  return (
    <section id={id} className="flex flex-col gap-3 scroll-mt-4">
      <h2 className="border-l-2 border-primary pl-3 text-section-title font-semibold text-foreground">
        {title}
      </h2>
      <div className="flex flex-col gap-3 text-sub leading-relaxed text-muted-foreground">
        {children}
      </div>
    </section>
  )
}

export default function Terms() {
  useDocumentTitle('Terms of Service')

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="mx-auto max-w-2xl px-6 py-12 sm:px-10">
        {/* Back */}
        <Button variant="ghost" size="sm" asChild className="mb-8 -ml-2">
          <Link to="/">
            <Icon icon="fa-solid fa-arrow-left" wrapperClassName="size-4" />
            返回首頁
          </Link>
        </Button>

        {/* Header */}
        <div className="mb-10 flex flex-col gap-2">
          <h1 className="text-3xl font-bold">服務條款</h1>
          <p className="text-label text-muted-foreground">生效日期：{EFFECTIVE_DATE}</p>
          <p className="mt-2 text-sub leading-relaxed text-muted-foreground">
            使用 {SERVICE_NAME} 前，請詳細閱讀以下條款。繼續使用即表示您同意本條款的所有內容。
          </p>
        </div>

        <div className="flex flex-col gap-10">
          <Section id="service" title="1. 服務說明">
            <p>
              {SERVICE_NAME}（以下稱「本服務」）為一款 Twitch 與 Discord
              雙平台機器人管理服務，提供自訂指令、關鍵字自動回應、定時訊息、遊戲排隊、影片排隊、社群連結預覽、伺服器事件日誌等功能，協助實況主與社群管理者管理聊天室及
              Discord 伺服器互動。
            </p>
          </Section>

          <Section id="auth" title="2. 帳號與授權">
            <p>
              本服務透過 Twitch OAuth 授權登入，不儲存您的 Twitch
              密碼。登入後，本服務將取得以下權限：
            </p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>讀取您的頻道資訊（使用者名稱、頻道 ID）</li>
              <li>發送聊天訊息（代表機器人帳號）</li>
              <li>讀取頻道點數兌換事件</li>
              <li>讀取訂閱、追蹤等頻道事件</li>
            </ul>
            <p>您可隨時在 Twitch 設定中撤銷本服務的授權。</p>
          </Section>

          <Section id="rules" title="3. 使用規範">
            <p>您同意在使用本服務時遵守以下規定：</p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>不得利用本服務發送騷擾、歧視、仇恨或違法內容</li>
              <li>不得嘗試繞過本服務的安全機制或進行未授權存取</li>
              <li>不得將本服務用於 Twitch 或 Discord 服務條款所禁止的行為</li>
              <li>不得對本服務進行逆向工程或複製</li>
            </ul>
            <p>違反上述規定者，我們保留終止服務的權利。</p>
          </Section>

          <Section id="availability" title="4. 服務可用性">
            <p>
              本服務以「現狀」提供，不保證 100%
              的可用性。我們會盡力維護服務穩定，但不對因維護、升級或不可抗力因素導致的中斷負責。
            </p>
            <p>我們保留隨時修改、暫停或終止服務的權利，並將提前通知重大變更。</p>
          </Section>

          <Section id="disclaimer" title="5. 免責聲明">
            <p>
              本服務對因使用或無法使用服務所造成的任何損失（包括但不限於資料遺失、業務中斷）不承擔責任。
            </p>
            <p>
              本服務不對第三方平台（Twitch、Discord、YouTube、Instagram、Bilibili、TikTok、Threads
              等）的政策變更、API 調整或服務中斷所造成的功能影響負責。
            </p>
          </Section>

          <Section id="changes" title="6. 條款修改">
            <p>
              我們保留修改本服務條款的權利。條款更新後將於本頁面公告，重大修改將透過 Discord
              社群通知。繼續使用服務即表示接受新條款。
            </p>
          </Section>

          <Section id="contact" title="7. 聯絡我們">
            <p>
              若您對服務條款有任何疑問，請透過我們的{' '}
              <a
                href={CONTACT_DISCORD}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-4 hover:text-primary/80"
              >
                Discord 社群
              </a>{' '}
              聯絡我們。
            </p>
          </Section>
        </div>

        {/* Footer */}
        <div className="mt-12 flex gap-4 border-t border-border pt-6 text-label text-muted-foreground">
          <Link to="/privacy" className="hover:text-foreground hover:underline">
            隱私權政策
          </Link>
          <span>·</span>
          <Link to="/" className="hover:text-foreground hover:underline">
            回到首頁
          </Link>
        </div>
      </div>
    </div>
  )
}
