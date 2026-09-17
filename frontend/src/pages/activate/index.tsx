import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { REGEXP_ONLY_DIGITS } from 'input-otp'
import { toast } from 'sonner'

import { activateAccount, getActivationRequestStatus, getPendingActivationCode } from '@/api/user'
import authorAvatarSrc from '@/assets/images/Author.jpg'
import { FadeIn, Icon, Spinner } from '@/components/primitives'
import {
  Avatar,
  AvatarFallback,
  AvatarImage,
  Button,
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  Separator,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type Gate = 'needs-grant' | 'rejected' | 'suspended'

interface ActivatePageProps {
  preview?: boolean
}

const twitchChannelUrl = 'https://www.twitch.tv/llazypilot'
const discordCommunityUrl = import.meta.env.VITE_DISCORD_COMMUNITY_URL?.trim()

function DiscordCommunityButton({
  className,
  label = 'Discord 社群',
}: {
  className?: string
  label?: string
}) {
  const content = (
    <>
      <Icon icon="fa-brands fa-discord" size="sm" />
      {label}
    </>
  )

  if (!discordCommunityUrl) {
    return (
      <Button variant="outline" className={className} disabled title="尚未設定 Discord 社群連結">
        {content}
      </Button>
    )
  }

  return (
    <Button asChild variant="outline" className={className}>
      <a href={discordCommunityUrl} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    </Button>
  )
}

interface TwitchActivationBlockProps {
  onRecheck: () => void
  recheckLoading: boolean
}

function TwitchActivationBlock({ onRecheck, recheckLoading }: TwitchActivationBlockProps) {
  return (
    <section
      aria-label="Twitch 獎勵啟用"
      className="bg-muted flex flex-col gap-section rounded-lg p-section sm:p-card"
    >
      <div className="flex items-center gap-element">
        <Avatar className="bg-card size-14 border">
          <AvatarImage src={authorAvatarSrc} alt="皮先森ツ（Niibot 作者）" />
          <AvatarFallback>皮</AvatarFallback>
        </Avatar>
        <div className="min-w-0">
          <h2 className="text-card-title font-semibold">皮先森ツ</h2>
          <p className="text-label text-muted-foreground">@llazypilot · Niibot 作者</p>
        </div>
      </div>

      <p className="text-sub text-muted-foreground">
        在 Twitch 兌換「Niibot」獎勵後，回到這裡確認。
      </p>

      <div className="flex flex-col gap-element">
        <div className="grid gap-element sm:grid-cols-2">
          <Button asChild>
            <a href={twitchChannelUrl} target="_blank" rel="noopener noreferrer">
              <Icon icon="fa-brands fa-twitch" size="sm" />
              前往 Twitch 兌換
            </a>
          </Button>
          <DiscordCommunityButton label="需要協助？前往 Discord 社群" />
        </div>
        <Button variant="outline" className="w-full" onClick={onRecheck} disabled={recheckLoading}>
          {recheckLoading ? <Spinner /> : null}
          確認是否已啟用
        </Button>
      </div>
    </section>
  )
}

export default function ActivatePage({ preview = false }: ActivatePageProps) {
  useDocumentTitle('啟用帳號')
  const { user, isInitialized, isAuthenticated, refreshUser, logout } = useAuth()
  const navigate = useNavigate()
  const isPreview = preview && import.meta.env.DEV

  const [gate, setGate] = useState<Gate>('needs-grant')
  const [statusLoading, setStatusLoading] = useState(!isPreview)

  const [showCode, setShowCode] = useState(false)
  const [code, setCode] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [pendingCode, setPendingCode] = useState<string | null>(null)
  const [pendingCodeLoading, setPendingCodeLoading] = useState(false)

  const [recheckLoading, setRecheckLoading] = useState(false)

  useEffect(() => {
    if (isPreview || !isInitialized || !isAuthenticated) return
    getActivationRequestStatus()
      .then(res => {
        if (res.status === 'rejected') setGate('rejected')
        else if (res.status === 'suspended') setGate('suspended')
        else setGate('needs-grant')
      })
      .catch(() => setGate('needs-grant'))
      .finally(() => setStatusLoading(false))
  }, [isInitialized, isAuthenticated, isPreview])

  if (!isPreview) {
    if (!isInitialized) return null
    if (!isAuthenticated) return <Navigate to="/login" replace />
    if (statusLoading) return null
    if (user?.is_activated || user?.is_owner) return <Navigate to="/dashboard" replace />
  }

  const handleRecheck = async () => {
    if (isPreview) {
      toast.info('預覽模式：正式頁面會重新確認兌換狀態')
      return
    }
    setRecheckLoading(true)
    try {
      const fresh = await refreshUser()
      if (fresh?.is_activated) {
        navigate('/dashboard', { replace: true })
        return
      }
      toast.info('尚未偵測到兌換紀錄，請確認已在頻道兌換 Niibot 獎勵')
    } catch {
      toast.error('無法確認狀態，請稍後再試')
    } finally {
      setRecheckLoading(false)
    }
  }

  const handleOtpSubmit = async () => {
    if (code.length !== 6) return
    if (isPreview) {
      toast.info('預覽模式：正式頁面會使用這組啟用碼啟用帳號')
      return
    }
    setOtpLoading(true)
    try {
      await activateAccount(code)
      await refreshUser()
      toast.success('帳號已啟用！')
      navigate('/dashboard', { replace: true })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'activation_failed'
      toast.error(
        msg === 'invalid_or_expired_code'
          ? '啟用碼無效或已過期，請確認後重試'
          : '啟用失敗，請稍後再試'
      )
      setCode('')
    } finally {
      setOtpLoading(false)
    }
  }

  const handleViewCode = async () => {
    if (isPreview) {
      setPendingCode('123456')
      setCode('123456')
      return
    }
    setPendingCodeLoading(true)
    try {
      const fetched = await getPendingActivationCode()
      if (fetched) {
        setPendingCode(fetched)
        setCode(fetched)
      } else {
        toast.info('目前沒有待用的啟用碼')
      }
    } catch {
      toast.error('無法取得啟用碼，請稍後再試')
    } finally {
      setPendingCodeLoading(false)
    }
  }

  const handleExit = () => {
    if (isPreview) {
      navigate('/')
      return
    }
    void logout()
  }

  return (
    <div className="bg-background flex min-h-svh items-center justify-center p-page md:p-page-lg">
      <FadeIn className="w-full max-w-lg">
        <Card className="overflow-hidden">
          <CardHeader className="items-center justify-items-center gap-element text-center">
            {gate === 'suspended' ? (
              <>
                <div className="flex items-center justify-center size-10 rounded-full bg-destructive/10">
                  <Icon icon="fa-solid fa-circle-pause" wrapperClassName="text-destructive" />
                </div>
                <h1 className="text-page-title font-bold">帳號已暫停</h1>
                <p className="text-sub text-muted-foreground text-balance">
                  你的帳號已被管理員暫停，請聯繫管理員以了解詳細原因。
                </p>
              </>
            ) : gate === 'rejected' ? (
              <>
                <div className="flex items-center justify-center size-10 rounded-full bg-destructive/10">
                  <Icon icon="fa-solid fa-circle-xmark" wrapperClassName="text-destructive" />
                </div>
                <h1 className="text-page-title font-bold">帳號目前無法啟用</h1>
                <p className="text-sub text-muted-foreground text-balance">
                  你的帳號目前無法使用 Niibot，請聯繫管理員。
                </p>
              </>
            ) : (
              <>
                <div className="flex items-center justify-center size-10 rounded-full bg-primary/10">
                  <Icon icon="fa-solid fa-gift" wrapperClassName="text-primary" />
                </div>
                <h1 className="text-page-title font-bold">啟用你的帳號</h1>
                <p className="text-sub text-muted-foreground max-w-[48ch] text-balance">
                  使用 Twitch 獎勵或啟用碼完成啟用。
                </p>
              </>
            )}
          </CardHeader>

          <CardContent className="flex flex-col gap-section pb-card">
            {gate === 'needs-grant' ? (
              <>
                <TwitchActivationBlock onRecheck={handleRecheck} recheckLoading={recheckLoading} />

                <div className="flex items-center gap-element">
                  <Separator className="flex-1" />
                  <span className="text-label text-muted-foreground">或</span>
                  <Separator className="flex-1" />
                </div>

                <section
                  aria-label="啟用碼"
                  className="bg-muted flex w-full flex-col gap-section rounded-lg p-section sm:p-card"
                >
                  <div className="flex flex-col gap-element">
                    <h2 className="text-card-title font-semibold">使用啟用碼</h2>
                    <p className="text-sub text-muted-foreground">輸入作者提供的 6 位數啟用碼。</p>
                  </div>

                  {showCode ? (
                    <>
                      {pendingCode ? (
                        <output className="font-mono text-page-title font-bold tracking-widest">
                          {pendingCode}
                        </output>
                      ) : (
                        <Button
                          variant="outline"
                          className="w-full"
                          onClick={handleViewCode}
                          disabled={pendingCodeLoading}
                        >
                          {pendingCodeLoading ? <Spinner /> : null}
                          查看啟用碼
                        </Button>
                      )}
                      <div className="flex w-full flex-col gap-element">
                        <InputOTP
                          aria-label="6 位啟用碼"
                          autoComplete="one-time-code"
                          inputMode="numeric"
                          maxLength={6}
                          pattern={REGEXP_ONLY_DIGITS}
                          value={code}
                          onChange={setCode}
                          onComplete={handleOtpSubmit}
                          disabled={otpLoading}
                          containerClassName="w-full justify-center"
                        >
                          <InputOTPGroup className="w-full max-w-xs">
                            {[0, 1, 2, 3, 4, 5].map(i => (
                              <InputOTPSlot key={i} index={i} className="min-w-0 flex-1" />
                            ))}
                          </InputOTPGroup>
                        </InputOTP>
                        <Button
                          className="w-full"
                          disabled={code.length !== 6 || otpLoading}
                          onClick={handleOtpSubmit}
                        >
                          {otpLoading ? '啟用中...' : '啟用帳號'}
                        </Button>
                      </div>
                    </>
                  ) : (
                    <Button className="w-full" onClick={() => setShowCode(true)}>
                      使用啟用碼
                    </Button>
                  )}
                </section>
              </>
            ) : (
              <DiscordCommunityButton className="w-full" />
            )}
          </CardContent>

          <CardFooter className="justify-center border-t">
            <Button variant="link" size="sm" onClick={handleExit} className="text-muted-foreground">
              {isPreview ? '返回首頁' : '登出'}
            </Button>
          </CardFooter>
        </Card>
      </FadeIn>
    </div>
  )
}
