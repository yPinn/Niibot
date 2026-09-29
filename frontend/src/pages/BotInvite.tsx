import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { declineBotInvite, getPublicBotInvite, type PublicBotInvite } from '@/api/botAccounts'
import { assertTrustedOAuthUrl } from '@/api/config'
import { FadeIn, Icon, Spinner } from '@/components/primitives'
import { TwitchAccountIdentity } from '@/components/TwitchAccountIdentity'
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
  if (status === 'declined') return '邀請已拒絕'
  if (status === 'authorized') return '授權已完成'
  return '邀請已過期'
}

function purposeIntro(purpose: PublicBotInvite['purpose'], name: string, channelName: string) {
  if (purpose === 'reauthorize') {
    return `${name} 邀請你重新授權這個 Twitch 帳號，讓 Niibot 繼續在 @${channelName} 發言。`
  }
  if (purpose === 'system_default_reset') {
    return '請重新授權這個 Twitch 帳號，讓 Niibot 繼續使用。'
  }
  return `${name} 想使用您的帳號，作為該頻道的機器人帳號。`
}

export default function BotInvite() {
  useDocumentTitle('機器人授權邀請')
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
  const profileName = invite ? invite.display_name || invite.channel_name : ''
  const consentPoints = invite
    ? [
        {
          icon: 'fa-solid fa-comments',
          label: '會做什麼',
          description: isSystemReset
            ? 'Niibot 會用這個帳號發言並執行必要的管理操作。'
            : `Niibot 會用這個帳號在 @${invite.channel_name} 發言；若它是頻道管理員，也能執行管理操作。`,
        },
        {
          icon: 'fa-solid fa-link',
          label: '可用頻道',
          description: isSystemReset
            ? '這次只會更新 Niibot 的系統機器人授權。'
            : `只供 @${invite.channel_name} 使用；其他頻道需要你另外同意。`,
        },
        {
          icon: 'fa-solid fa-shield-halved',
          label: '撤回授權',
          description: isSystemReset
            ? 'Niibot 不會取得你的 Twitch 密碼。你可隨時撤回授權；撤回後，使用系統機器人的頻道會停止相關功能。'
            : 'Niibot 不會取得你的 Twitch 密碼。你可隨時撤回授權；撤回後，使用此帳號的頻道會停止相關功能。',
        },
      ]
    : []

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-page md:p-page-lg">
      <FadeIn className="w-full max-w-xl">
        <Card className="overflow-hidden">
          <CardHeader className="grid grid-cols-[auto_1fr] items-start gap-section pb-card text-left">
            <div className="bg-primary/10 flex size-10 items-center justify-center rounded-full">
              <Icon icon="fa-solid fa-robot" wrapperClassName="text-primary" />
            </div>
            <div className="space-y-element">
              <h1 className="text-page-title font-bold">授權 Twitch 帳號擔任機器人</h1>
              <CardDescription className="max-w-[44ch]">
                確認後，Niibot 會依下列方式使用你的帳號。
              </CardDescription>
            </div>
          </CardHeader>

          <CardContent className="flex flex-col gap-card pb-card">
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
                  aria-label={isSystemReset ? '系統機器人帳號' : '邀請頻道'}
                  className="bg-muted/70 flex flex-col gap-card rounded-lg p-card"
                >
                  <TwitchAccountIdentity
                    avatar={invite.avatar}
                    displayName={profileName}
                    login={invite.channel_name}
                    label={isSystemReset ? '系統機器人帳號' : '邀請頻道'}
                    size="large"
                  />
                  <p className="max-w-[48ch] text-sub leading-relaxed text-muted-foreground">
                    {purposeIntro(invite.purpose, profileName, invite.channel_name)}
                  </p>
                </section>

                <div aria-label="授權重點" className="divide-y">
                  {consentPoints.map(point => (
                    <section
                      key={point.label}
                      className="grid grid-cols-[2.5rem_1fr] gap-section py-section first:pt-0 last:pb-0"
                    >
                      <div className="bg-muted flex size-10 items-center justify-center rounded-full">
                        <Icon
                          icon={point.icon}
                          size="sm"
                          wrapperClassName="text-muted-foreground"
                        />
                      </div>
                      <div className="max-w-[48ch] space-y-element">
                        <h2 className="text-content font-semibold">{point.label}</h2>
                        <p className="text-sub leading-relaxed text-muted-foreground">
                          {point.description}
                        </p>
                      </div>
                    </section>
                  ))}
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
                      請使用專用的機器人帳號，不要使用頻道主帳號。
                    </p>
                  </div>
                )}

                <div className="space-y-section border-t pt-card">
                  <p className="text-center text-label text-muted-foreground">
                    此連結只能使用一次，{formatDateTimeShort(invite.expires_at)} 前有效。
                  </p>
                  <div className="grid gap-element sm:grid-cols-2">
                    <Button
                      size="lg"
                      variant="outline"
                      onClick={() => void decline()}
                      disabled={declining}
                    >
                      {declining && <Spinner className="mr-2" />}
                      拒絕邀請
                    </Button>
                    {oauthUrl ? (
                      <Button size="lg" asChild>
                        <a href={oauthUrl}>
                          <Icon icon="fa-brands fa-twitch" size="sm" />
                          前往 Twitch 授權
                        </a>
                      </Button>
                    ) : (
                      <Button size="lg" disabled>
                        授權連結無效
                      </Button>
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
