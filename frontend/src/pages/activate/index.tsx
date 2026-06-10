import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import {
  activateAccount,
  getActivationRequestStatus,
  getPendingActivationCode,
  requestActivation,
} from '@/api/user'
import {
  Button,
  Card,
  CardContent,
  FadeIn,
  Icon,
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
  Separator,
  Spinner,
} from '@/components/ui'
import { useAuth } from '@/contexts/AuthContext'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

type RequestStatus = 'pending' | 'rejected'

export default function ActivatePage() {
  useDocumentTitle('Activate Account')
  const { user, isInitialized, isAuthenticated, refreshUser, logout } = useAuth()
  const navigate = useNavigate()

  const [code, setCode] = useState('')
  const [otpLoading, setOtpLoading] = useState(false)

  const [pendingCode, setPendingCode] = useState<string | null>(null)
  const [pendingCodeLoading, setPendingCodeLoading] = useState(false)

  const [requestStatus, setRequestStatus] = useState<RequestStatus>('pending')
  const [reapplyLoading, setReapplyLoading] = useState(false)
  const [statusLoading, setStatusLoading] = useState(true)

  useEffect(() => {
    if (!isInitialized || !isAuthenticated) return
    getActivationRequestStatus()
      .then(async res => {
        if (res.status === 'rejected') {
          setRequestStatus('rejected')
        } else if (!res.status) {
          // No request yet (edge case) — auto-create one
          try {
            await requestActivation()
          } catch {
            // best-effort — page still shows pending state regardless
          }
        }
        // pending or auto-created → default state is already 'pending'
      })
      .catch(() => {})
      .finally(() => setStatusLoading(false))
  }, [isInitialized, isAuthenticated])

  if (!isInitialized) return null
  if (!isAuthenticated) return <Navigate to="/login" replace />
  if (statusLoading) return null
  if (user?.is_activated || user?.is_owner) return <Navigate to="/dashboard" replace />

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

  const handleReapply = async () => {
    setReapplyLoading(true)
    try {
      await requestActivation()
      setRequestStatus('pending')
    } catch {
      toast.error('送出申請失敗，請稍後再試')
    } finally {
      setReapplyLoading(false)
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
        toast.info('目前沒有待用的啟用碼，請先兌換頻道點數！')
      }
    } catch {
      toast.error('無法取得啟用碼，請稍後再試')
    } finally {
      setPendingCodeLoading(false)
    }
  }

  const handleCheckApproval = async () => {
    try {
      const freshUser = await refreshUser()
      if (freshUser?.is_activated) {
        navigate('/dashboard', { replace: true })
      } else {
        const res = await getActivationRequestStatus()
        if (res.status === 'rejected') setRequestStatus('rejected')
        else toast.info('申請尚未審核，請稍後再試')
      }
    } catch {
      toast.error('無法取得狀態，請稍後再試')
    }
  }

  return (
    <div className="bg-muted flex min-h-svh flex-col items-center justify-center p-4 md:p-page-lg">
      <FadeIn className="w-full max-w-sm">
        <Card>
          <CardContent className="flex flex-col items-center gap-6 p-6 sm:p-8">
            {/* ── OTP section ── */}
            <div className="flex flex-col items-center gap-2 text-center w-full">
              <h1 className="text-page-title font-bold">輸入啟用碼</h1>
              <p className="text-muted-foreground text-balance text-sub">
                請輸入透過 Twitch 頻道點數兌換後取得的 6 位數啟用碼
              </p>
            </div>

            {pendingCode ? (
              <div className="flex flex-col items-center gap-1 w-full">
                <p className="text-label text-muted-foreground">你的啟用碼</p>
                <p className="font-mono text-page-title font-bold tracking-widest">{pendingCode}</p>
              </div>
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
                <InputOTPSlot index={0} />
                <InputOTPSlot index={1} />
                <InputOTPSlot index={2} />
                <InputOTPSlot index={3} />
                <InputOTPSlot index={4} />
                <InputOTPSlot index={5} />
              </InputOTPGroup>
            </InputOTP>

            <Button
              className="w-full"
              disabled={code.length !== 6 || otpLoading}
              onClick={handleOtpSubmit}
            >
              {otpLoading ? '啟用中...' : '啟用帳號'}
            </Button>

            {/* ── Divider ── */}
            <div className="flex w-full items-center gap-3">
              <Separator className="flex-1" />
              <span className="text-label text-muted-foreground shrink-0">或</span>
              <Separator className="flex-1" />
            </div>

            {/* ── Request status section ── */}
            {requestStatus === 'rejected' ? (
              <div className="flex flex-col items-center gap-3 text-center w-full">
                <div className="flex items-center justify-center size-10 rounded-full bg-destructive/10">
                  <Icon icon="fa-solid fa-circle-xmark" wrapperClassName="text-destructive" />
                </div>
                <div>
                  <p className="font-medium text-sub">申請未通過</p>
                  <p className="text-label text-muted-foreground mt-0.5">
                    你可以重新送出申請，或使用啟用碼。
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleReapply}
                  disabled={reapplyLoading}
                >
                  {reapplyLoading ? <Spinner className="mr-1.5" /> : null}
                  重新申請
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 text-center w-full">
                <div className="flex items-center justify-center size-10 rounded-full bg-status-loading/10">
                  <Icon icon="fa-solid fa-clock" wrapperClassName="text-status-loading" />
                </div>
                <div>
                  <p className="font-medium text-sub">申請等待審核中</p>
                  <p className="text-label text-muted-foreground mt-0.5">
                    審核通過後即可使用，您也可以先輸入啟用碼。
                  </p>
                </div>
                <Button variant="outline" size="sm" onClick={handleCheckApproval}>
                  確認審核狀態
                </Button>
              </div>
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
