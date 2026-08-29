import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { activateAccount, getActivationRequestStatus, getPendingActivationCode } from '@/api/user'
import { FadeIn, Icon, Spinner } from '@/components/primitives'
import { Button, Card, CardContent, InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type Gate = 'needs-grant' | 'rejected' | 'suspended'

export default function ActivatePage() {
  useDocumentTitle('Activate Account')
  const { user, isInitialized, isAuthenticated, refreshUser, logout } = useAuth()
  const navigate = useNavigate()

  const [gate, setGate] = useState<Gate>('needs-grant')
  const [statusLoading, setStatusLoading] = useState(true)

  const [showCode, setShowCode] = useState(false)
  const [code, setCode] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)
  const [pendingCode, setPendingCode] = useState<string | null>(null)
  const [pendingCodeLoading, setPendingCodeLoading] = useState(false)

  const [recheckLoading, setRecheckLoading] = useState(false)

  useEffect(() => {
    if (!isInitialized || !isAuthenticated) return
    getActivationRequestStatus()
      .then(res => {
        if (res.status === 'rejected') setGate('rejected')
        else if (res.status === 'suspended') setGate('suspended')
        else setGate('needs-grant')
      })
      .catch(() => setGate('needs-grant'))
      .finally(() => setStatusLoading(false))
  }, [isInitialized, isAuthenticated])

  if (!isInitialized) return null
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (statusLoading) return null
  if (user?.is_activated || user?.is_owner) return <Navigate to="/dashboard" replace />

  const handleRecheck = async () => {
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

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-4 md:p-page-lg">
      <FadeIn className="w-full max-w-sm">
        <Card>
          <CardContent className="flex flex-col items-center gap-6 p-6 sm:p-8">
            {gate === 'suspended' ? (
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="flex items-center justify-center size-10 rounded-full bg-destructive/10">
                  <Icon icon="fa-solid fa-circle-pause" wrapperClassName="text-destructive" />
                </div>
                <h1 className="text-page-title font-bold">帳號已暫停</h1>
                <p className="text-sub text-muted-foreground text-balance">
                  你的帳號已被管理員暫停，請聯繫管理員以了解詳細原因。
                </p>
              </div>
            ) : gate === 'rejected' ? (
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="flex items-center justify-center size-10 rounded-full bg-destructive/10">
                  <Icon icon="fa-solid fa-circle-xmark" wrapperClassName="text-destructive" />
                </div>
                <h1 className="text-page-title font-bold">授權未通過</h1>
                <p className="text-sub text-muted-foreground text-balance">
                  你的帳號目前無法使用 Niibot，請聯繫管理員。
                </p>
              </div>
            ) : (
              <>
                <div className="flex flex-col items-center gap-2 text-center">
                  <div className="flex items-center justify-center size-10 rounded-full bg-primary/10">
                    <Icon icon="fa-solid fa-gift" wrapperClassName="text-primary" />
                  </div>
                  <h1 className="text-page-title font-bold">啟用你的帳號</h1>
                  <p className="text-sub text-muted-foreground text-balance">
                    到 Niibot 的 Twitch 頻道兌換「Niibot」頻道點數獎勵，之後重新登入即會自動啟用。
                  </p>
                </div>

                <Button className="w-full" onClick={handleRecheck} disabled={recheckLoading}>
                  {recheckLoading ? <Spinner className="mr-1.5" /> : null}
                  我已兌換，重新確認
                </Button>

                {showCode ? (
                  <div className="flex w-full flex-col items-center gap-4">
                    <p className="text-label text-muted-foreground text-center text-balance">
                      若你收到管理員給的啟用碼，請在此輸入
                    </p>
                    {pendingCode ? (
                      <p className="font-mono text-page-title font-bold tracking-widest">
                        {pendingCode}
                      </p>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        onClick={handleViewCode}
                        disabled={pendingCodeLoading}
                      >
                        {pendingCodeLoading ? <Spinner className="mr-1.5" /> : null}
                        查看我的啟用碼
                      </Button>
                    )}
                    <InputOTP
                      maxLength={6}
                      value={code}
                      onChange={setCode}
                      onComplete={handleOtpSubmit}
                      disabled={otpLoading}
                    >
                      <InputOTPGroup>
                        {[0, 1, 2, 3, 4, 5].map(i => (
                          <InputOTPSlot key={i} index={i} />
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
                ) : (
                  <button
                    onClick={() => setShowCode(true)}
                    className="text-muted-foreground hover:text-foreground text-label underline underline-offset-4 transition-colors"
                  >
                    我有啟用碼
                  </button>
                )}
              </>
            )}

            <button
              onClick={logout}
              className="text-muted-foreground hover:text-foreground text-label underline underline-offset-4 transition-colors"
            >
              登出
            </button>
          </CardContent>
        </Card>
      </FadeIn>
    </div>
  )
}
