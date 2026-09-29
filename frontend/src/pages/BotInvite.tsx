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
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useSensitivePageMetadata } from '@/hooks/useSensitivePageMetadata'
import { formatDateTimeShort } from '@/lib/format'

function terminalMessage(status: PublicBotInvite['status']) {
  if (status === 'declined') return '已拒絕這次 Bot 授權邀請'
  if (status === 'authorized') return '這次 Bot 授權已經完成'
  return '這個 Bot 授權邀請已過期'
}

/** 第一句：說明這封邀請要你做什麼。Twitch 授權頁不會交代這件事。 */
function purposeIntro(purpose: PublicBotInvite['purpose'], name: string) {
  if (purpose === 'reauthorize') {
    return `${name} 邀請你更新 Bot 授權，讓 Niibot 繼續在其頻道運作。`
  }
  if (purpose === 'system_default_reset') {
    return '請使用這個帳號更新 Niibot 的系統 Bot 授權。'
  }
  return `${name} 邀請你讓 Niibot 以你的 Twitch 帳號，在其頻道擔任聊天機器人。`
}

const CAPABILITY_SUMMARY: { icon: string; text: string }[] = [
  { icon: 'fa-solid fa-comments', text: '以你的帳號讀寫聊天室訊息、執行指令與發送公告' },
  {
    icon: 'fa-solid fa-gavel',
    text: '在你具備 MOD 身分時執行禁言、封鎖等管理操作',
  },
  { icon: 'fa-solid fa-users', text: '讀取運作所需的追隨、訂閱與聊天室資訊' },
]

export default function BotInvite() {
  useDocumentTitle('Bot 授權邀請')
  useSensitivePageMetadata()
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

  const isSystemReset = invite?.purpose === 'system_default_reset'

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-page md:p-page-lg">
      <FadeIn className="w-full max-w-2xl">
        <Card className="overflow-hidden">
          <CardHeader className="grid grid-cols-[auto_1fr] items-start gap-section text-left">
            <div className="bg-primary/10 flex size-10 items-center justify-center rounded-full">
              <Icon icon="fa-solid fa-robot" wrapperClassName="text-primary" />
            </div>
            <div className="space-y-1">
              <h1 className="text-page-title font-bold">授權 Bot 帳號</h1>
              <CardDescription className="max-w-[52ch]">
                確認這個帳號會如何使用，再前往 Twitch 完成授權。
              </CardDescription>
            </div>
          </CardHeader>

          <CardContent className="flex flex-col gap-section pb-card">
            {capabilityError || (error && !invite) ? (
              <Alert variant="destructive">
                <AlertDescription>{capabilityError || error}</AlertDescription>
              </Alert>
            ) : !invite ? (
              <div className="flex min-h-40 items-center justify-center" aria-label="載入授權邀請">
                <Spinner />
              </div>
            ) : invite.status !== 'pending' ? (
              <div
                className="bg-muted flex items-center justify-center gap-element rounded-lg p-card text-center text-sub font-medium"
                role="status"
              >
                <Icon
                  icon="fa-solid fa-circle-info"
                  size="sm"
                  wrapperClassName="text-muted-foreground"
                />
                {terminalMessage(invite.status)}
              </div>
            ) : (
              <>
                {error && (
                  <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                )}

                <section
                  aria-labelledby="invite-account"
                  className="bg-muted grid gap-element rounded-lg p-section sm:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] sm:items-center"
                >
                  <div className="flex min-w-0 items-center gap-element">
                    <div className="bg-background flex size-9 shrink-0 items-center justify-center rounded-full">
                      <Icon icon="fa-brands fa-twitch" size="sm" wrapperClassName="text-primary" />
                    </div>
                    <div className="min-w-0">
                      <p id="invite-account" className="text-label text-muted-foreground">
                        {isSystemReset ? '系統 Bot 帳號' : '邀請頻道'}
                      </p>
                      <p className="truncate text-sub font-semibold">
                        {invite.display_name || invite.channel_name}
                      </p>
                      <p className="truncate font-mono text-label text-muted-foreground">
                        @{invite.channel_name}
                      </p>
                    </div>
                  </div>
                  <p className="text-sub text-muted-foreground">
                    {purposeIntro(invite.purpose, invite.display_name || invite.channel_name)}
                  </p>
                </section>

                <div className="grid gap-section md:grid-cols-2">
                  <section
                    aria-labelledby="invite-capabilities"
                    className="space-y-element border-b pb-section md:border-r md:border-b-0 md:pr-section md:pb-0"
                  >
                    <h2 id="invite-capabilities" className="text-sub font-semibold">
                      授權後
                    </h2>
                    <ul className="space-y-element">
                      {CAPABILITY_SUMMARY.map(item => (
                        <li key={item.text} className="flex items-start gap-element text-sub">
                          <Icon
                            icon={item.icon}
                            size="sm"
                            wrapperClassName="mt-0.5 text-muted-foreground"
                          />
                          <span>{item.text}</span>
                        </li>
                      ))}
                    </ul>
                  </section>

                  <section aria-labelledby="invite-boundaries" className="space-y-element">
                    <h2 id="invite-boundaries" className="text-sub font-semibold">
                      使用範圍
                    </h2>
                    <ul className="space-y-element text-sub text-muted-foreground">
                      {isSystemReset ? (
                        <>
                          <li>這次只會更新 Niibot 的系統 Bot 授權，不會建立 Dashboard 帳號。</li>
                          <li>Niibot 不會取得 Twitch 密碼；授權資料會加密保存。</li>
                          <li>若從 Twitch 撤銷授權，使用這個系統 Bot 的頻道都會停止相關功能。</li>
                        </>
                      ) : (
                        <>
                          <li>
                            只同意 <span className="font-mono">@{invite.channel_name}</span>{' '}
                            使用這個 Bot；其他頻道仍需你個別同意。
                          </li>
                          <li>Niibot 不會取得 Twitch 密碼，也不會替你建立 Dashboard 帳號。</li>
                          <li>
                            邀請人可停止本頻道使用；若從 Twitch 撤銷授權，所有使用這個 Bot
                            的頻道都會停止相關功能。
                          </li>
                        </>
                      )}
                      <li>連結只能使用一次，{formatDateTimeShort(invite.expires_at)} 前有效。</li>
                    </ul>
                  </section>
                </div>

                {!isSystemReset && (
                  <div
                    className="bg-status-warning/10 flex items-start gap-element rounded-lg p-section text-sub text-status-warning"
                    role="note"
                  >
                    <Icon
                      icon="fa-solid fa-triangle-exclamation"
                      size="sm"
                      wrapperClassName="mt-0.5"
                    />
                    <p className="text-status-warning">
                      請使用專用 Bot 帳號。若同一 Twitch 帳號已用來管理自己的 Niibot
                      頻道，授權會失敗。
                    </p>
                  </div>
                )}

                <div className="space-y-element border-t pt-section">
                  <p className="text-center text-label text-muted-foreground">
                    Twitch 會在下一頁列出精確權限。
                  </p>
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
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  )
}
