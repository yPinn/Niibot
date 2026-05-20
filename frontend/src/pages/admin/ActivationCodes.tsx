import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type ActivationRequest,
  approveActivationRequest,
  getActivationRequests,
  getPendingActivationCodes,
  type PendingCode,
  rejectActivationRequest,
  revokeActivationCode,
} from '@/api/admin'
import { PageHeader } from '@/components/PageHeader'
import { PageMain } from '@/components/PageMain'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardHeader,
  CardTitle,
  Icon,
  Separator,
  Skeleton,
  SlideUp,
  Spinner,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ── Activation Requests ───────────────────────────────────────────────────────

function RequestsCard() {
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [actioningId, setActioningId] = useState<number | null>(null)
  const [confirmReject, setConfirmReject] = useState<ActivationRequest | null>(null)

  const fetchRequests = useCallback(async () => {
    setLoading(true)
    try {
      setRequests(await getActivationRequests())
    } catch {
      setRequests([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchRequests().catch(() => undefined)
  }, [fetchRequests])

  const handleApprove = async (req: ActivationRequest) => {
    setActioningId(req.id)
    try {
      await approveActivationRequest(req.id)
      setRequests(prev => prev.filter(r => r.id !== req.id))
      toast.success(`${req.display_name ?? req.username ?? req.platform_user_id} 已通過審核`)
    } catch {
      toast.error('審核失敗')
    } finally {
      setActioningId(null)
    }
  }

  const handleReject = async (req: ActivationRequest) => {
    setActioningId(req.id)
    setConfirmReject(null)
    try {
      await rejectActivationRequest(req.id)
      setRequests(prev => prev.filter(r => r.id !== req.id))
      toast.success('申請已拒絕')
    } catch {
      toast.error('操作失敗')
    } finally {
      setActioningId(null)
    }
  }

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Icon
              icon="fa-solid fa-user-check"
              size="sm"
              wrapperClassName="text-muted-foreground"
            />
            <CardTitle className="text-card-title">授權申請</CardTitle>
          </div>
          <CardAction>
            <div className="flex items-center gap-2">
              {requests.length > 0 && (
                <Badge className="border-status-loading/20 bg-status-loading/10 text-status-loading font-mono text-label">
                  {requests.length} 待審
                </Badge>
              )}
              <Button
                variant="ghost"
                size="icon"
                onClick={() => void fetchRequests()}
                aria-label="Refresh"
              >
                <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
              </Button>
            </div>
          </CardAction>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {Array.from({ length: 2 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full" />
              ))}
            </div>
          ) : requests.length === 0 ? (
            <p className="text-sub text-muted-foreground py-2">目前沒有待審核的申請。</p>
          ) : (
            requests.map((req, idx) => {
              const label = req.display_name ?? req.username ?? req.platform_user_id
              const isActioning = actioningId === req.id
              return (
                <div key={req.id}>
                  {idx > 0 && <Separator className="opacity-40" />}
                  <div className="flex items-start gap-3 py-3">
                    {req.avatar ? (
                      <img
                        src={req.avatar}
                        alt={label}
                        className="size-8 rounded-full shrink-0 object-cover mt-0.5"
                      />
                    ) : (
                      <div className="size-8 rounded-full bg-muted shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-baseline gap-2">
                        <p className="text-sub font-medium truncate">{label}</p>
                        <p className="text-label text-muted-foreground font-mono shrink-0">
                          {new Date(req.created_at).toLocaleString('zh-TW', {
                            month: '2-digit',
                            day: '2-digit',
                            hour: '2-digit',
                            minute: '2-digit',
                            hour12: false,
                          })}
                        </p>
                      </div>
                      {req.note && (
                        <p className="text-label text-muted-foreground mt-0.5 wrap-break-word">
                          {req.note}
                        </p>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-status-online border-status-online/30 hover:bg-status-online/10"
                        onClick={() => handleApprove(req)}
                        disabled={isActioning}
                      >
                        {isActioning ? <Spinner /> : <Icon icon="fa-solid fa-check" size="xs" />}
                        通過
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-destructive border-destructive/30 hover:bg-destructive/10"
                        onClick={() => setConfirmReject(req)}
                        disabled={isActioning}
                      >
                        拒絕
                      </Button>
                    </div>
                  </div>
                </div>
              )
            })
          )}
        </CardContent>
      </Card>

      <AlertDialog open={!!confirmReject} onOpenChange={open => !open && setConfirmReject(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>確定拒絕申請？</AlertDialogTitle>
            <AlertDialogDescription>
              將拒絕{' '}
              <span className="font-medium text-foreground">
                {confirmReject?.display_name ??
                  confirmReject?.username ??
                  confirmReject?.platform_user_id}
              </span>{' '}
              的授權申請。對方可以重新送出申請。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => confirmReject && handleReject(confirmReject)}
            >
              拒絕
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

// ── Pending OTP Codes ─────────────────────────────────────────────────────────

function CodesCard() {
  const [codes, setCodes] = useState<PendingCode[]>([])
  const [loading, setLoading] = useState(true)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState(0)

  const fetchCodes = useCallback(async () => {
    setLoading(true)
    try {
      setCodes(await getPendingActivationCodes())
      setNowMs(Date.now())
    } catch {
      setCodes([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCodes().catch(() => undefined)
  }, [fetchCodes])

  const handleRevoke = useCallback(async (platformUserId: string) => {
    setRevoking(platformUserId)
    try {
      await revokeActivationCode(platformUserId)
      setCodes(prev => prev.filter(c => c.platform_user_id !== platformUserId))
    } finally {
      setRevoking(null)
    }
  }, [])

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-2">
          <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">待使用啟用碼</CardTitle>
        </div>
        <CardAction>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-mono text-label">
              {loading ? '…' : codes.length}
            </Badge>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => void fetchCodes()}
              aria-label="Refresh"
            >
              <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : codes.length === 0 ? (
          <p className="text-sub text-muted-foreground py-2">目前沒有待使用的啟用碼。</p>
        ) : (
          codes.map((code, idx) => {
            const label = code.display_name ?? code.username ?? code.platform_user_id
            const expiresMs = new Date(code.expires_at).getTime()
            const hoursLeft = Math.max(0, Math.round((expiresMs - nowMs) / 3_600_000))
            const isExpiringSoon = hoursLeft <= 12
            const expiryLabel = new Date(code.expires_at).toLocaleString('zh-TW', {
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })
            const isRevoking = revoking === code.platform_user_id
            return (
              <div key={code.platform_user_id + code.expires_at}>
                {idx > 0 && <Separator className="opacity-40" />}
                <div className="flex items-center gap-3 py-2">
                  {code.avatar ? (
                    <img
                      src={code.avatar}
                      alt={label}
                      className="size-7 rounded-full shrink-0 object-cover"
                    />
                  ) : (
                    <div className="size-7 rounded-full bg-muted shrink-0" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-sub font-medium truncate">{label}</p>
                    <p className="text-label text-muted-foreground font-mono truncate">
                      {code.platform_user_id}
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {code.code_plain && (
                      <p className="font-mono text-sub font-bold tracking-widest">
                        {code.code_plain}
                      </p>
                    )}
                    <div className="text-right">
                      <Badge
                        variant="outline"
                        className={`font-mono text-label ${
                          isExpiringSoon ? 'border-status-offline/30 text-status-offline' : ''
                        }`}
                      >
                        {hoursLeft}h 後過期
                      </Badge>
                      <p className="text-label text-muted-foreground font-mono mt-0.5">
                        {expiryLabel}
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      size="icon"
                      disabled={isRevoking}
                      onClick={() => void handleRevoke(code.platform_user_id)}
                      aria-label="撤銷啟用碼"
                    >
                      <Icon
                        icon={isRevoking ? 'fa-solid fa-spinner fa-spin' : 'fa-solid fa-ban'}
                        wrapperClassName="text-muted-foreground"
                      />
                    </Button>
                  </div>
                </div>
              </div>
            )
          })
        )}
      </CardContent>
    </Card>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminActivationCodes() {
  useDocumentTitle('Activation')

  return (
    <PageMain className="lg:gap-card">
      <PageHeader
        title="Activation"
        description="審核授權申請，管理透過點數兌換產生的 OTP 啟用碼。"
      />
      <div className="grid grid-cols-1 gap-card items-start md:grid-cols-[3fr_2fr]">
        <SlideUp>
          <RequestsCard />
        </SlideUp>
        <SlideUp>
          <CodesCard />
        </SlideUp>
      </div>
    </PageMain>
  )
}
