import { Link } from 'react-router-dom'

import { Icon } from '@/components/primitives'
import { Button } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

const EFFECTIVE_DATE = '2026 年 4 月 23 日'
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

export default function Privacy() {
  useDocumentTitle('Privacy Policy')

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
          <h1 className="text-3xl font-bold">隱私權政策</h1>
          <p className="text-label text-muted-foreground">生效日期：{EFFECTIVE_DATE}</p>
          <p className="mt-2 text-sub leading-relaxed text-muted-foreground">
            本政策說明 Niibot 如何蒐集、使用及保護您的個人資料。使用本服務即表示您同意本政策。
          </p>
        </div>

        <div className="flex flex-col gap-10">
          <Section id="collection" title="1. 我們蒐集哪些資料">
            <p>當您使用 Niibot 時，我們會蒐集以下資料：</p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>
                <strong className="text-foreground">Twitch 帳號資訊：</strong>
                使用者名稱、頻道 ID、顯示名稱、大頭貼（由 Twitch OAuth 授權提供）
              </li>
              <li>
                <strong className="text-foreground">頻道活動資料：</strong>
                訂閱者、追蹤者、Bits 贊助、頻道點數兌換等事件記錄
              </li>
              <li>
                <strong className="text-foreground">機器人設定資料：</strong>
                您建立的自訂指令、自動回應、定時訊息、模組設定
              </li>
              <li>
                <strong className="text-foreground">使用紀錄：</strong>
                指令觸發次數、功能使用統計（用於數據分析）
              </li>
              <li>
                <strong className="text-foreground">Discord 成員生日：</strong>
                由成員主動透過 Discord Bot 指令提供，僅用於生日提醒功能
              </li>
              <li>
                <strong className="text-foreground">Discord 伺服器事件日誌：</strong>
                訊息刪除與編輯的操作紀錄、成員身分組異動（不儲存訊息原文內容）
              </li>
            </ul>
            <p>我們不蒐集您的 Twitch 或 Discord 密碼，亦不蒐集任何財務相關資訊。</p>
          </Section>

          <Section id="usage" title="2. 資料如何使用">
            <p>我們使用蒐集的資料用於：</p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>提供並維護 Niibot 的核心功能（指令回應、事件自動化、伺服器日誌等）</li>
              <li>顯示頻道數據分析（觀眾趨勢、指令使用統計）</li>
              <li>改善服務品質與功能穩定性</li>
              <li>排查技術問題與錯誤</li>
            </ul>
            <p>我們不會將您的資料出售給第三方，亦不用於廣告目的。</p>
          </Section>

          <Section id="storage" title="3. 資料儲存與安全">
            <p>
              您的設定資料儲存於安全的資料庫伺服器，並透過加密連線傳輸。我們採取合理的技術措施保護您的資料安全。
            </p>
            <p>Twitch OAuth Token 以加密方式儲存於後端，僅用於代表機器人操作您授權的頻道功能。</p>
          </Section>

          <Section id="retention" title="4. 資料保留期限">
            <p>
              您的帳號資料將在您使用服務期間保留。停止使用並撤銷 Twitch
              授權後，我們將在合理期限內（最長 90 天）刪除您的個人資料。
            </p>
            <p>Discord 成員生日資料可由成員本人或伺服器管理員隨時刪除。</p>
            <p>匿名的使用統計資料（不含個人識別資訊）可能長期保留用於服務改善。</p>
          </Section>

          <Section id="third-party" title="5. 第三方服務">
            <p>本服務整合以下第三方平台，各平台有其獨立的隱私政策：</p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>
                <strong className="text-foreground">Twitch：</strong>
                提供 OAuth 登入、聊天室 API 與頻道事件
              </li>
              <li>
                <strong className="text-foreground">Discord：</strong>
                提供 Discord Bot 服務、伺服器指令與事件日誌功能
              </li>
              <li>
                <strong className="text-foreground">YouTube、Bilibili、Twitch：</strong>
                影片排隊功能用於向這些平台發送請求以解析影片資訊
              </li>
              <li>
                <strong className="text-foreground">Instagram、Bilibili、TikTok、Threads：</strong>
                社群連結預覽功能會向這些平台發送公開請求以取得嵌入資訊，不儲存相關用戶資料
              </li>
            </ul>
            <p>我們建議您同時閱讀這些平台的隱私政策。</p>
          </Section>

          <Section id="rights" title="6. 您的權利">
            <p>您對自己的資料擁有以下權利：</p>
            <ul className="ml-4 flex list-disc flex-col gap-1">
              <li>
                <strong className="text-foreground">存取權：</strong>
                查閱我們儲存的您的資料
              </li>
              <li>
                <strong className="text-foreground">更正權：</strong>
                要求更正不正確的資料
              </li>
              <li>
                <strong className="text-foreground">刪除權：</strong>
                要求刪除您的帳號及相關資料
              </li>
              <li>
                <strong className="text-foreground">撤銷授權：</strong>
                隨時在 Twitch 設定中撤銷本服務的 OAuth 授權
              </li>
            </ul>
            <p>
              如需行使上述權利，請透過我們的{' '}
              <a
                href={CONTACT_DISCORD}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-4 hover:text-primary/80"
              >
                Discord 社群
              </a>{' '}
              提出申請。
            </p>
          </Section>

          <Section id="cookies" title="7. Cookie 使用">
            <p>
              本服務使用 Cookie 維持您的登入狀態（Session Cookie）。這些 Cookie
              在您登出後即失效。我們不使用追蹤型或廣告型 Cookie。
            </p>
          </Section>

          <Section id="updates" title="8. 隱私政策更新">
            <p>
              我們可能不定期更新本隱私權政策。重大變更將透過 Discord
              社群通知，並於本頁面更新生效日期。繼續使用服務即表示接受更新後的政策。
            </p>
          </Section>

          <Section id="contact" title="9. 聯絡我們">
            <p>
              若您對隱私政策有任何疑問或需要行使資料權利，請透過我們的{' '}
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
          <Link to="/terms" className="hover:text-foreground hover:underline">
            服務條款
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
