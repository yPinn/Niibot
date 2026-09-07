import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { declineBotInvite, getPublicBotInvite, type PublicBotInvite } from '@/api/botAccounts'
import { assertTrustedOAuthUrl } from '@/api/config'
import { FadeIn, Icon, Spinner } from '@/components/primitives'
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatDateTimeShort } from '@/lib/format'

function terminalMessage(status: PublicBotInvite['status']) {
  if (status === 'declined') return '已拒絕這次 Bot 授權邀請'
  if (status === 'authorized') return '這次 Bot 授權已經完成'
  return '這個 Bot 授權邀請已過期'
}

/** 第一句：說明這封邀請要你做什麼。Twitch 授權頁不會交代這件事。 */
function purposeIntro(purpose: PublicBotInvite['purpose'], name: string) {
  if (purpose === 'reauthorize') {
    return `${name} 請你重新授權這個 Bot 帳號 —— 原本的 Twitch 憑證已失效或需要更新權限。`
  }
  if (purpose === 'system_default_reset') {
    return '請你重新授權 Niibot 的系統預設 Bot 帳號。'
  }
  return `${name} 想在自己的頻道，用你的 Twitch 帳號當聊天機器人。`
}

/** 11 條 scope 收斂成給一般人看的白話。純顯示用，Twitch 會在下一頁列出精確權限。 */
const CAPABILITY_SUMMARY: { icon: string; text: string; caution?: boolean }[] = [
  { icon: 'fa-solid fa-comments', text: '在聊天室讀取訊息、發送機器人回覆與指令' },
  { icon: 'fa-solid fa-bullhorn', text: '發送公告、shoutout 與悄悄話' },
  {
    icon: 'fa-solid fa-gavel',
    text: '若你是該頻道的 MOD，可代你執行禁言、封鎖等審核動作',
    caution: true,
  },
  { icon: 'fa-solid fa-users', text: '讀取追隨者、在線觀眾、訂閱與表情資訊' },
]

export default function BotInvite() {
  useDocumentTitle('Bot 授權邀請')
  const { publicToken = '' } = useParams()
  const [searchParams] = useSearchParams()
  const nonce = searchParams.get('nonce') ?? ''
  const [invite, setInvite] = useState<PublicBotInvite | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [declining, setDeclining] = useState(false)
  const capabilityError = !publicToken || !nonce ? '這個授權連結不完整' : null

  useEffect(() => {
    let active = true
    if (!publicToken || !nonce) return
    void getPublicBotInvite(publicToken, nonce)
      .then(result => {
        if (active) setInvite(result)
      })
      .catch(() => {
        if (active) setError('無法讀取這個授權邀請，請向邀請人索取新連結')
      })
    return () => {
      active = false
    }
  }, [nonce, publicToken])

  const decline = async () => {
    setDeclining(true)
    try {
      await declineBotInvite(publicToken, nonce)
      setInvite(current =>
        current ? { ...current, status: 'declined', oauth_url: null } : current
      )
    } catch {
      setError('拒絕邀請失敗，請稍後再試')
    } finally {
      setDeclining(false)
    }
  }

  let oauthUrl: string | null = null
  if (invite?.oauth_url) {
    try {
      oauthUrl = assertTrustedOAuthUrl(invite.oauth_url, 'twitch')
    } catch {
      oauthUrl = null
    }
  }

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-page md:p-page-lg">
      <FadeIn className="w-full max-w-lg">
        <Card className="overflow-hidden">
          <CardHeader className="items-center justify-items-center gap-element text-center">
            <div className="flex size-10 items-center justify-center rounded-full bg-primary/10">
              <Icon icon="fa-solid fa-robot" wrapperClassName="text-primary" />
            </div>
            <h1 className="text-page-title font-bold">授權 Bot 帳號</h1>
            <CardDescription className="max-w-[48ch] text-balance">
              有人邀請你，把 Twitch 帳號借給他的頻道當聊天機器人。看完再決定要不要前往 Twitch 授權。
            </CardDescription>
          </CardHeader>

          <CardContent className="flex flex-col gap-section pb-card">
            {capabilityError || error ? (
              <Alert variant="destructive">
                <AlertDescription>{capabilityError || error}</AlertDescription>
              </Alert>
            ) : !invite ? (
              <div className="flex min-h-40 items-center justify-center" aria-label="載入授權邀請">
                <Spinner />
              </div>
            ) : invite.status !== 'pending' ? (
              <div className="bg-muted rounded-lg p-card text-center text-sub font-medium">
                {terminalMessage(invite.status)}
              </div>
            ) : (
              <>
                <section
                  aria-labelledby="invite-channel"
                  className="bg-muted flex flex-col gap-element rounded-lg p-section sm:p-card"
                >
                  <p id="invite-channel" className="text-label text-muted-foreground">
                    邀請來源
                  </p>
                  <div>
                    <p className="text-card-title font-semibold">
                      {invite.display_name || invite.channel_name}
                    </p>
                    <p className="font-mono text-label text-muted-foreground">
                      @{invite.channel_name}
                    </p>
                  </div>
                  <p className="text-sub text-muted-foreground">
                    {purposeIntro(invite.purpose, invite.display_name || invite.channel_name)}
                  </p>
                  {invite.purpose !== 'system_default_reset' && (
                    <p className="text-sub text-muted-foreground">
                      授權後，Niibot 會以你的身分在{' '}
                      <span className="font-mono text-foreground">@{invite.channel_name}</span>{' '}
                      的聊天室發言與執行指令 —— 觀眾看到的發言者會是你的帳號。
                    </p>
                  )}
                </section>

                <section
                  aria-labelledby="invite-capabilities"
                  className="flex flex-col gap-element"
                >
                  <h2 id="invite-capabilities" className="text-sub font-semibold">
                    Niibot 會用你的帳號做什麼
                  </h2>
                  <ul className="flex flex-col gap-element rounded-lg border p-section">
                    {CAPABILITY_SUMMARY.map(item => (
                      <li
                        key={item.text}
                        className={`flex items-start gap-element text-sub ${
                          item.caution ? 'text-status-warning' : ''
                        }`}
                      >
                        <Icon
                          icon={item.icon}
                          size="sm"
                          wrapperClassName={`mt-0.5 ${
                            item.caution ? 'text-status-warning' : 'text-muted-foreground'
                          }`}
                        />
                        <span>{item.text}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                <section aria-labelledby="invite-boundaries" className="flex flex-col gap-element">
                  <h2 id="invite-boundaries" className="text-sub font-semibold">
                    不會發生的事
                  </h2>
                  <ul className="flex flex-col gap-element text-sub text-muted-foreground">
                    <li>· 不會建立 Niibot 帳號，也不會給你 Dashboard 後台權限</li>
                    <li>
                      · 只在 <span className="font-mono">@{invite.channel_name}</span>{' '}
                      生效；其他實況主看不到、也不能使用你的帳號
                    </li>
                    <li>· 不會動到你自己的頻道</li>
                    <li>· 拿不到你的 Twitch 密碼；憑證加密保存，不會顯示給任何人</li>
                  </ul>
                </section>

                <section aria-labelledby="invite-revoke" className="flex flex-col gap-element">
                  <h2 id="invite-revoke" className="text-sub font-semibold">
                    你隨時可以收回
                  </h2>
                  <ul className="flex flex-col gap-element text-sub text-muted-foreground">
                    <li>· 這個連結一次性使用，{formatDateTimeShort(invite.expires_at)} 前有效</li>
                    <li>· 之後可到 Twitch【設定 → 連線】隨時撤銷授權</li>
                    <li>· 邀請人也可以隨時停止使用這個 Bot</li>
                  </ul>
                </section>

                <Collapsible className="rounded-lg border">
                  <CollapsibleTrigger className="group flex w-full items-center justify-between gap-element p-section text-sub font-medium">
                    <span>完整 Twitch 權限清單（{invite.required_scopes.length} 項）</span>
                    <Icon
                      icon="fa-solid fa-chevron-down"
                      size="xs"
                      wrapperClassName="text-muted-foreground transition-transform group-data-[state=open]:rotate-180"
                    />
                  </CollapsibleTrigger>
                  <CollapsibleContent className="border-t p-section pt-0">
                    <p className="py-element text-label text-muted-foreground">
                      Twitch 會在下一頁用自己的說明再列一次，以 Twitch 頁面顯示的為準。
                    </p>
                    <ul className="flex flex-col gap-element">
                      {invite.required_scopes.map(scope => (
                        <li key={scope} className="flex items-center gap-element text-label">
                          <Icon
                            icon="fa-solid fa-check"
                            size="xs"
                            wrapperClassName="text-status-online"
                          />
                          <code>{scope}</code>
                        </li>
                      ))}
                    </ul>
                  </CollapsibleContent>
                </Collapsible>

                <div className="grid gap-element sm:grid-cols-2">
                  <Button variant="outline" onClick={() => void decline()} disabled={declining}>
                    {declining && <Spinner className="mr-2" />}
                    拒絕邀請
                  </Button>
                  {oauthUrl ? (
                    <Button asChild>
                      <a href={oauthUrl}>
                        <Icon icon="fa-brands fa-twitch" size="sm" />
                        前往 Twitch 授權
                      </a>
                    </Button>
                  ) : (
                    <Button disabled>授權連結無效</Button>
                  )}
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  )
}
