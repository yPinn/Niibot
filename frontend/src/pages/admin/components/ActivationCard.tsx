import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type ActivationRequest,
  approveActivationRequest,
  createOwnerCode,
  getActivationRequests,
  getGrants,
  getMembershipTimeline,
  getOnboardingFunnel,
  type Grant,
  type GrantStatus,
  type MembershipEvent,
  type OnboardingFunnel,
  rejectActivationRequest,
  revokeGrant,
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
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { formatDateTimeShort } from '@/lib/format'
import { toastApiError } from '@/lib/toast-error'

const KIND_LABEL: Record<Grant['kind'], string> = {
  channel_points: '頻道點數',
  owner_manual: '手動發放',
}

const STATUS_LABEL: Record<GrantStatus, string> = {
  issued: '待使用',
  consumed: '已啟用',
  expired: '已過期',
  revoked: '已撤銷',
}

const STATUS_TONE: Record<GrantStatus, string> = {
  issued: 'border-status-loading/20 bg-status-loading/10 text-status-loading',
  consumed: 'border-status-online/20 bg-status-online/10 text-status-online',
  expired: 'text-muted-foreground',
  revoked: 'text-muted-foreground',
}

const EVENT_LABEL: Record<MembershipEvent['event_type'], string> = {
  requested: '提出申請',
  auto_admitted: '自動核准',
  approved: '核准',
  rejected: '駁回',
  suspended: '暫停',
  reinstated: '恢復',
  withdrawn: '撤回',
}

export function ActivationCard() {
  // ── funnel ──────────────────────────────────────────────────────────
  const [funnel, setFunnel] = useState<OnboardingFunnel | null>(null)

  // ── grants ──────────────────────────────────────────────────────────
  const [grants, setGrants] = useState<Grant[]>([])
  const [grantsLoading, setGrantsLoading] = useState(true)
  const [statusFilter, setStatusFilter] = useState<GrantStatus | 'all'>('issued')
  const [revoking, setRevoking] = useState<number | null>(null)
  const [issuing, setIssuing] = useState(false)

  // ── pending requests ───────────────────────────────────────────────
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [reqLoading, setReqLoading] = useState(true)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [confirmReject, setConfirmReject] = useState<ActivationRequest | null>(null)

  // ── timeline sheet ─────────────────────────────────────────────────
  const [timelineFor, setTimelineFor] = useState<{ userId: string; label: string } | null>(null)
  const [timeline, setTimeline] = useState<MembershipEvent[] | null>(null)

  const fetchFunnel = useCallback(async () => {
    try {
      setFunnel(await getOnboardingFunnel())
    } catch {
      /* non-critical */
    }
  }, [])

  const fetchGrants = useCallback(async (status: GrantStatus | 'all') => {
    try {
      setGrants(await getGrants(status === 'all' ? undefined : { status }))
    } catch {
      setGrants([])
    } finally {
      setGrantsLoading(false)
    }
  }, [])

  const fetchRequests = useCallback(async () => {
    try {
      setRequests(await getActivationRequests())
    } catch {
      setRequests([])
    } finally {
      setReqLoading(false)
    }
  }, [])

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    void fetchFunnel()
    void fetchRequests()
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [fetchFunnel, fetchRequests])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchGrants(statusFilter)
  }, [fetchGrants, statusFilter])

  const refreshAll = useCallback(() => {
    setGrantsLoading(true)
    setReqLoading(true)
    void fetchFunnel()
    void fetchGrants(statusFilter)
    void fetchRequests()
  }, [fetchFunnel, fetchGrants, fetchRequests, statusFilter])

  const handleStatusChange = (v: string) => {
    setGrantsLoading(true)
    setStatusFilter(v as GrantStatus | 'all')
  }

  const handleIssue = async () => {
    setIssuing(true)
    try {
      const code = await createOwnerCode()
      toast.success(`啟用碼：${code}`, { description: '72 小時內有效，單次使用', duration: 15000 })
      refreshAll()
    } catch (e) {
      toastApiError(e, '產生啟用碼失敗')
    } finally {
      setIssuing(false)
    }
  }

  const handleRevoke = async (id: number) => {
    setRevoking(id)
    try {
      await revokeGrant(id)
      setGrants(prev => prev.filter(g => g.id !== id))
      void fetchFunnel()
    } catch (e) {
      toastApiError(e, '撤銷失敗')
    } finally {
      setRevoking(null)
    }
  }

  const handleApprove = async (req: ActivationRequest) => {
    setActioningId(req.id)
    try {
      await approveActivationRequest(req.id)
      setRequests(prev => prev.filter(r => r.id !== req.id))
      void fetchFunnel()
      toast.success(`${req.display_name ?? req.username ?? req.platform_user_id} 已通過`)
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

  const openTimeline = async (userId: string, label: string) => {
    setTimelineFor({ userId, label })
    setTimeline(null)
    try {
      setTimeline(await getMembershipTimeline(userId))
    } catch (e) {
      toastApiError(e, '載入紀錄失敗')
      setTimeline([])
    }
  }

  const cp = funnel?.by_kind.find(k => k.kind === 'channel_points')
  const conversion =
    cp && cp.issued_30d > 0 ? Math.round((cp.consumed_30d / cp.issued_30d) * 100) : null

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-element">
              <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">授權管理</CardTitle>
            </div>
            <div className="flex items-center gap-element">
              <Button size="sm" variant="outline" onClick={handleIssue} disabled={issuing}>
                {issuing ? (
                  <Spinner className="mr-1.5" />
                ) : (
                  <Icon icon="fa-solid fa-plus" size="xs" />
                )}
                產生啟用碼
              </Button>
              <Button variant="ghost" size="icon" onClick={refreshAll} aria-label="Refresh">
                <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-section">
          {/* ── funnel ── */}
          <div className="grid grid-cols-3 gap-element">
            <Stat label="啟用中" value={funnel ? String(funnel.active_members) : '—'} />
            <Stat label="30 日兌換" value={cp ? `${cp.consumed_30d}/${cp.issued_30d}` : '—'} />
            <Stat label="轉換率" value={conversion === null ? '—' : `${conversion}%`} />
          </div>

          <Separator />

          {/* ── pending requests (operator tool; usually empty) ── */}
          {(reqLoading || requests.length > 0) && (
            <>
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
                  <Skeleton className="h-10 w-full" />
                ) : (
                  requests.map((req, idx) => {
                    const label = req.display_name ?? req.username ?? req.platform_user_id
                    const busy = actioningId === req.id
                    return (
                      <div key={req.id}>
                        {idx > 0 && <Separator className="opacity-40" />}
                        <div className="flex items-center gap-3 py-3">
                          <Avatar src={req.avatar} label={label} />
                          <div className="flex-1 min-w-0">
                            <p className="text-sub font-medium truncate">{label}</p>
                            <p className="text-label text-muted-foreground font-mono">
                              {formatDateTimeShort(req.created_at)}
                            </p>
                          </div>
                          <div className="flex items-center gap-element shrink-0">
                            <Button
                              variant="ghost"
                              size="icon"
                              aria-label="授權紀錄"
                              onClick={() => openTimeline(req.id, label)}
                            >
                              <Icon
                                icon="fa-solid fa-clock-rotate-left"
                                wrapperClassName="text-muted-foreground"
                              />
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="text-status-online border-status-online/30 hover:bg-status-online/10"
                              onClick={() => handleApprove(req)}
                              disabled={busy}
                            >
                              {busy ? <Spinner /> : <Icon icon="fa-solid fa-check" size="xs" />}
                              通過
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              className="text-destructive border-destructive/30 hover:bg-destructive/10"
                              onClick={() => setConfirmReject(req)}
                              disabled={busy}
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
            </>
          )}

          {/* ── grants ── */}
          <div>
            <div className="flex items-center justify-between mb-section">
              <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                啟用碼
              </span>
              <Tabs value={statusFilter} onValueChange={handleStatusChange}>
                <TabsList>
                  <TabsTrigger value="issued">待使用</TabsTrigger>
                  <TabsTrigger value="consumed">已啟用</TabsTrigger>
                  <TabsTrigger value="all">全部</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>

            {grantsLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-11 w-full" />
                ))}
              </div>
            ) : grants.length === 0 ? (
              <p className="text-sub text-muted-foreground py-1">沒有符合的啟用碼。</p>
            ) : (
              grants.map((g, idx) => {
                const label = g.display_name ?? g.username ?? g.platform_user_id ?? '（未綁定）'
                const when =
                  g.status === 'issued'
                    ? `${formatDateTimeShort(g.expires_at)} 到期`
                    : g.used_at
                      ? formatDateTimeShort(g.used_at)
                      : formatDateTimeShort(g.expires_at)
                return (
                  <div key={g.id}>
                    {idx > 0 && <Separator className="opacity-40" />}
                    <div className="flex items-center gap-3 py-2">
                      <Avatar src={g.avatar} label={label} size={7} />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-element">
                          <p className="text-sub font-medium truncate">{label}</p>
                          <Badge variant="outline" className="text-label shrink-0">
                            {KIND_LABEL[g.kind]}
                          </Badge>
                        </div>
                        <p className="text-label text-muted-foreground font-mono truncate">
                          {when}
                          {g.reward_cost != null ? ` · ${g.reward_cost} pts` : ''}
                        </p>
                      </div>
                      <div className="flex items-center gap-element shrink-0">
                        {g.code_plain && (
                          <span className="font-mono text-sub font-bold tracking-widest">
                            {g.code_plain}
                          </span>
                        )}
                        <Badge variant="outline" className={`text-label ${STATUS_TONE[g.status]}`}>
                          {STATUS_LABEL[g.status]}
                        </Badge>
                        {g.status === 'issued' && (
                          <Button
                            variant="ghost"
                            size="icon"
                            disabled={revoking === g.id}
                            onClick={() => handleRevoke(g.id)}
                            aria-label="撤銷"
                          >
                            <Icon
                              icon={
                                revoking === g.id
                                  ? 'fa-solid fa-spinner fa-spin'
                                  : 'fa-solid fa-ban'
                              }
                              wrapperClassName="text-muted-foreground"
                            />
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </CardContent>
      </Card>

      <Sheet open={!!timelineFor} onOpenChange={open => !open && setTimelineFor(null)}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>{timelineFor?.label} · 授權紀錄</SheetTitle>
          </SheetHeader>
          <div className="p-4 space-y-3">
            {timeline === null ? (
              <Spinner />
            ) : timeline.length === 0 ? (
              <p className="text-sub text-muted-foreground">沒有紀錄。</p>
            ) : (
              timeline.map(ev => (
                <div key={ev.id} className="flex items-start gap-3">
                  <div className="mt-1 size-2 rounded-full bg-primary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sub font-medium">
                      {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                      <span className="text-label text-muted-foreground font-normal ml-2">
                        {ev.actor_type}
                      </span>
                    </p>
                    <p className="text-label text-muted-foreground font-mono">
                      {formatDateTimeShort(ev.occurred_at)}
                      {ev.reason ? ` · ${ev.reason}` : ''}
                    </p>
                  </div>
                </div>
              ))
            )}
          </div>
        </SheetContent>
      </Sheet>

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
            的授權申請。
          </>
        }
        actionLabel="拒絕"
        onConfirm={() => confirmReject && handleReject(confirmReject)}
      />
    </>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2">
      <p className="text-label text-muted-foreground">{label}</p>
      <p className="text-sub font-bold font-mono">{value}</p>
    </div>
  )
}

function Avatar({ src, label, size = 8 }: { src: string | null; label: string; size?: 7 | 8 }) {
  const box = size === 7 ? 'size-7' : 'size-8'
  return src ? (
    <img src={src} alt={label} className={`${box} rounded-full shrink-0 object-cover`} />
  ) : (
    <div className={`${box} rounded-full bg-muted shrink-0`} />
  )
}
