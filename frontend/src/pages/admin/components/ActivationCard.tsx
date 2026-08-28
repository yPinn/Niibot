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
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { Icon, Spinner } from '@/components/primitives'
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Separator,
  Skeleton,
} from '@/components/ui'
import { formatDateTimeShort } from '@/lib/format'
import { toastApiError } from '@/lib/toast-error'

export function ActivationCard() {
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [reqLoading, setReqLoading] = useState(true)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [confirmReject, setConfirmReject] = useState<ActivationRequest | null>(null)

  const fetchRequests = useCallback(async () => {
    setReqLoading(true)
    try {
      setRequests(await getActivationRequests())
    } catch {
      setRequests([])
    } finally {
      setReqLoading(false)
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
    } catch (e) {
      toastApiError(e, '審核失敗')
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
    } catch (e) {
      toastApiError(e, '操作失敗')
    } finally {
      setActioningId(null)
    }
  }

  const [codes, setCodes] = useState<PendingCode[]>([])
  const [codesLoading, setCodesLoading] = useState(true)
  const [revoking, setRevoking] = useState<string | null>(null)
  const [nowMs, setNowMs] = useState(() => Date.now())

  const fetchCodes = useCallback(async () => {
    setCodesLoading(true)
    try {
      setCodes(await getPendingActivationCodes())
      setNowMs(Date.now())
    } catch {
      setCodes([])
    } finally {
      setCodesLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchCodes().catch(() => undefined)
  }, [fetchCodes])

  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(id)
  }, [])

  const handleRevoke = useCallback(async (platformUserId: string) => {
    setRevoking(platformUserId)
    try {
      await revokeActivationCode(platformUserId)
      setCodes(prev => prev.filter(c => c.platform_user_id !== platformUserId))
    } catch (e) {
      toastApiError(e, '撤銷失敗')
    } finally {
      setRevoking(null)
    }
  }, [])

  const handleRefresh = useCallback(() => {
    void fetchRequests()
    void fetchCodes()
  }, [fetchRequests, fetchCodes])

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-element">
              <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">授權管理</CardTitle>
            </div>
            <Button variant="ghost" size="icon" onClick={handleRefresh} aria-label="Refresh">
              <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-section">
          {/* ── 授權申請 ── */}
          <div>
            <div className="flex items-center gap-element mb-section">
              <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                授權申請
              </span>
              {requests.length > 0 && (
                <Badge className="border-status-loading/20 bg-status-loading/10 text-status-loading font-mono text-label">
                  {requests.length} 待審
                </Badge>
              )}
            </div>
            {reqLoading ? (
              <div>
                {Array.from({ length: 2 }).map((_, i) => (
                  <div key={i}>
                    {i > 0 && <Separator className="opacity-40" />}
                    <div className="flex items-start gap-3 py-3">
                      <Skeleton className="size-8 rounded-full shrink-0 mt-0.5" />
                      <div className="flex-1 space-y-1.5 min-w-0">
                        <Skeleton className="h-4 w-32" />
                        <Skeleton className="h-3 w-20" />
                      </div>
                      <div className="flex items-center gap-element shrink-0">
                        <Skeleton className="h-7 w-14 rounded-md" />
                        <Skeleton className="h-7 w-10 rounded-md" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : requests.length === 0 ? (
              <p className="text-sub text-muted-foreground py-1">目前沒有待審核的申請。</p>
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
                        <div className="flex items-baseline gap-element">
                          <p className="text-sub font-medium truncate">{label}</p>
                          <p className="text-label text-muted-foreground font-mono shrink-0">
                            {formatDateTimeShort(req.created_at)}
                          </p>
                        </div>
                        {req.note && (
                          <p className="text-label text-muted-foreground mt-0.5 wrap-break-word">
                            {req.note}
                          </p>
                        )}
                      </div>
                      <div className="flex items-center gap-element shrink-0">
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
          </div>

          <Separator />

          {/* ── 待使用啟用碼 ── */}
          <div>
            <div className="flex items-center gap-element mb-section">
              <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                待使用啟用碼
              </span>
              <Badge variant="outline" className="font-mono text-label">
                {codesLoading ? '…' : codes.length}
              </Badge>
            </div>
            {codesLoading ? (
              <div>
                {Array.from({ length: 3 }).map((_, i) => (
                  <div key={i}>
                    {i > 0 && <Separator className="opacity-40" />}
                    <div className="flex items-center gap-3 py-2">
                      <Skeleton className="size-7 rounded-full shrink-0" />
                      <div className="flex-1 space-y-1 min-w-0">
                        <Skeleton className="h-4 w-28" />
                        <Skeleton className="h-3 w-24" />
                      </div>
                      <div className="flex items-center gap-element shrink-0">
                        <Skeleton className="h-4 w-10" />
                        <div className="space-y-1">
                          <Skeleton className="h-5 w-16 rounded-full" />
                          <Skeleton className="h-3 w-12" />
                        </div>
                        <Skeleton className="size-8 rounded-md" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : codes.length === 0 ? (
              <p className="text-sub text-muted-foreground py-1">目前沒有待使用的啟用碼。</p>
            ) : (
              codes.map((code, idx) => {
                const label = code.display_name ?? code.username ?? code.platform_user_id
                const expiresMs = new Date(code.expires_at).getTime()
                const hoursLeft = Math.max(0, Math.round((expiresMs - nowMs) / 3_600_000))
                const isExpiringSoon = hoursLeft <= 12
                const expiryLabel = formatDateTimeShort(code.expires_at)
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
                      <div className="flex items-center gap-element shrink-0">
                        {code.code_plain && (
                          <p className="font-mono text-sub font-bold tracking-widest">
                            {code.code_plain}
                          </p>
                        )}
                        <div className="text-right">
                          <Badge
                            variant="outline"
                            className={`font-mono text-label ${isExpiringSoon ? 'border-status-offline/30 text-status-offline' : ''}`}
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
          </div>
        </CardContent>
      </Card>

      <DeleteConfirmDialog
        open={!!confirmReject}
        onOpenChange={open => !open && setConfirmReject(null)}
        title="確定拒絕申請？"
        description={
          <>
            將拒絕{' '}
            <span className="font-medium text-foreground">
              {confirmReject?.display_name ??
                confirmReject?.username ??
                confirmReject?.platform_user_id}
            </span>{' '}
            的授權申請。對方可以重新送出申請。
          </>
        }
        actionLabel="拒絕"
        onConfirm={() => confirmReject && handleReject(confirmReject)}
      />
    </>
  )
}
