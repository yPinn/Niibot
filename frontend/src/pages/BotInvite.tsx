import { useEffect, useState } from 'react'
import { useParams, useSearchParams } from 'react-router-dom'

import { declineBotInvite, getPublicBotInvite, type PublicBotInvite } from '@/api/botAccounts'
import { assertTrustedOAuthUrl } from '@/api/config'
import { Icon, Spinner } from '@/components/primitives'
import { Button, Card, CardContent, CardDescription, CardHeader } from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

function terminalMessage(status: PublicBotInvite['status']) {
  if (status === 'declined') return '已拒絕這次 Bot 授權邀請'
  if (status === 'authorized') return '這次 Bot 授權已經完成'
  return '這個 Bot 授權邀請已過期'
}

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
    <main className="min-h-svh bg-background px-4 py-10 sm:py-16">
      <Card className="mx-auto w-full max-w-xl">
        <CardHeader className="text-center">
          <div className="mx-auto mb-2 grid size-12 place-items-center rounded-full bg-primary/10 text-primary">
            <Icon icon="fa-solid fa-robot" size="lg" />
          </div>
          <h1 className="text-page-title font-semibold">授權 Bot 帳號</h1>
          <CardDescription>
            只提供 Twitch Bot 憑證，不會建立 Niibot 帳號或 Dashboard 權限。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-section">
          {capabilityError || error ? (
            <div
              role="alert"
              className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm"
            >
              {capabilityError || error}
            </div>
          ) : !invite ? (
            <div className="flex min-h-40 items-center justify-center" aria-label="載入授權邀請">
              <Spinner />
            </div>
          ) : invite.status !== 'pending' ? (
            <div className="rounded-lg bg-muted p-5 text-center font-medium">
              {terminalMessage(invite.status)}
            </div>
          ) : (
            <>
              <section
                aria-labelledby="invite-channel"
                className="rounded-lg border bg-muted/40 p-4"
              >
                <p id="invite-channel" className="text-label text-muted-foreground">
                  邀請來源
                </p>
                <p className="mt-1 text-card-title font-semibold">
                  {invite.display_name || invite.channel_name}
                </p>
                <p className="font-mono text-label text-muted-foreground">@{invite.channel_name}</p>
              </section>

              <section aria-labelledby="requested-scopes">
                <h2 id="requested-scopes" className="mb-2 text-sub font-semibold">
                  將授予的 Twitch 權限
                </h2>
                <ul className="max-h-56 space-y-1 overflow-y-auto rounded-lg border p-3">
                  {invite.required_scopes.map(scope => (
                    <li key={scope} className="flex items-center gap-2 text-label">
                      <Icon icon="fa-solid fa-check" size="xs" className="text-status-online" />
                      <code>{scope}</code>
                    </li>
                  ))}
                </ul>
              </section>

              <p className="text-label text-muted-foreground">
                授權後，邀請人只能在自己的頻道選用這個 Bot；其他租戶不會看見它。
              </p>

              <div className="grid gap-2 sm:grid-cols-2">
                <Button variant="outline" onClick={() => void decline()} disabled={declining}>
                  {declining && <Spinner className="mr-2" />}
                  拒絕邀請
                </Button>
                {oauthUrl ? (
                  <Button asChild>
                    <a href={oauthUrl}>前往 Twitch 授權</a>
                  </Button>
                ) : (
                  <Button disabled>授權連結無效</Button>
                )}
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
