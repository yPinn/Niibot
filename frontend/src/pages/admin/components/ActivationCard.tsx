import { type ReactNode, useCallback, useEffect, useState } from 'react'
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
import { EmptyState, Icon, Spinner } from '@/components/primitives'
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
  suspended: '停權',
  reinstated: '恢復',
  withdrawn: '撤回',
}

const ACTOR_LABEL: Record<MembershipEvent['actor_type'], string> = {
  system: '系統',
  owner: '管理員',
  user: '使用者',
}

export function ActivationCard() {
  // ── funnel ──────────────────────────────────────────────────────────
  const [funnel, setFunnel] = useState<OnboardingFunnel | null>(null)
  const [funnelLoading, setFunnelLoading] = useState(true)
  const [funnelError, setFunnelError] = useState(false)

  // ── grants ──────────────────────────────────────────────────────────
  const [grants, setGrants] = useState<Grant[]>([])
  const [grantsLoading, setGrantsLoading] = useState(true)
  const [grantsError, setGrantsError] = useState(false)
  const [statusFilter, setStatusFilter] = useState<GrantStatus | 'all'>('issued')
  const [revoking, setRevoking] = useState<number | null>(null)
  const [issuing, setIssuing] = useState(false)

  // ── pending requests ───────────────────────────────────────────────
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [reqLoading, setReqLoading] = useState(true)
  const [reqError, setReqError] = useState(false)
  const [actioningId, setActioningId] = useState<string | null>(null)
  const [confirmReject, setConfirmReject] = useState<ActivationRequest | null>(null)

  // ── timeline sheet ─────────────────────────────────────────────────
  const [timelineFor, setTimelineFor] = useState<{ userId: string; label: string } | null>(null)
  const [timeline, setTimeline] = useState<MembershipEvent[] | null>(null)

  const fetchFunnel = useCallback(async () => {
    setFunnelError(false)
    try {
      setFunnel(await getOnboardingFunnel())
    } catch {
      setFunnel(null)
      setFunnelError(true)
    } finally {
      setFunnelLoading(false)
    }
  }, [])

  const fetchGrants = useCallback(async (status: GrantStatus | 'all') => {
    setGrantsError(false)
    try {
      setGrants(await getGrants(status === 'all' ? undefined : { status }))
    } catch {
      setGrants([])
      setGrantsError(true)
    } finally {
      setGrantsLoading(false)
    }
  }, [])

  const fetchRequests = useCallback(async () => {
    setReqError(false)
    try {
      setRequests(await getActivationRequests())
    } catch {
      setRequests([])
      setReqError(true)
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
    setFunnelLoading(true)
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

  const retryFunnel = () => {
    setFunnelLoading(true)
    void fetchFunnel()
  }

  const retryRequests = () => {
    setReqLoading(true)
    void fetchRequests()
  }

  const retryGrants = () => {
    setGrantsLoading(true)
    void fetchGrants(statusFilter)
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
  const showRequests = reqLoading || reqError || requests.length > 0

  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex flex-col gap-section sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-element">
              <Icon icon="fa-solid fa-key" size="sm" wrapperClassName="text-muted-foreground" />
              <div className="space-y-1">
                <CardTitle className="text-card-title">授權管理</CardTitle>
                <p className="text-label text-muted-foreground">
                  檢視授權成效、處理申請，並管理可使用的啟用碼。
                </p>
              </div>
            </div>
            <div className="flex items-center gap-element self-start sm:self-auto">
              <Button size="sm" variant="outline" onClick={handleIssue} disabled={issuing}>
                {issuing ? (
                  <Spinner className="mr-1.5" />
                ) : (
                  <Icon icon="fa-solid fa-plus" size="xs" />
                )}
                產生啟用碼
              </Button>
              <Button
                variant="ghost"
                size="icon"
                onClick={refreshAll}
                aria-label="重新整理授權資料"
              >
                <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-card">
          <section aria-label="授權摘要" className="space-y-element">
            <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border bg-border lg:grid-cols-4">
              <Stat
                label="有效使用者"
                value={funnel ? String(funnel.active_members) : '—'}
                loading={funnelLoading}
              />
              <Stat
                label="近 30 日已發出"
                value={cp ? String(cp.issued_30d) : '—'}
                loading={funnelLoading}
              />
              <Stat
                label="近 30 日已啟用"
                value={cp ? String(cp.consumed_30d) : '—'}
                loading={funnelLoading}
              />
              <Stat
                label="啟用率"
                value={conversion === null ? '—' : `${conversion}%`}
                loading={funnelLoading}
              />
            </dl>
            {funnelError && (
              <ErrorState
                message="授權摘要載入失敗"
                actionLabel="重試授權摘要"
                onRetry={retryFunnel}
              />
            )}
          </section>

          <Separator />

          <div
            role="group"
            aria-label="授權作業"
            className={`grid items-start gap-card ${showRequests ? 'xl:grid-cols-2' : ''}`}
          >
            {showRequests && (
              <section
                aria-labelledby="activation-requests-title"
                className="min-w-0 space-y-element"
              >
                <div className="flex items-center gap-element">
                  <h3 id="activation-requests-title" className="text-sub font-semibold">
                    授權申請
                  </h3>
                  {requests.length > 0 && (
                    <Badge className="border-status-loading/20 bg-status-loading/10 text-status-loading text-label">
                      {requests.length} 待審
                    </Badge>
                  )}
                </div>
                {reqLoading ? (
                  <div className="space-y-2">
                    {Array.from({ length: 2 }).map((_, i) => (
                      <Skeleton key={i} className="h-16 w-full rounded-lg" />
                    ))}
                  </div>
                ) : reqError ? (
                  <ErrorState
                    message="授權申請載入失敗"
                    actionLabel="重試授權申請"
                    onRetry={retryRequests}
                  />
                ) : (
                  <div className="divide-y overflow-hidden rounded-lg border">
                    {requests.map(req => {
                      const label = req.display_name ?? req.username ?? req.platform_user_id
                      const busy = actioningId === req.id
                      return (
                        <div
                          key={req.id}
                          className="flex flex-col gap-section px-3 py-3 sm:flex-row sm:items-center"
                        >
                          <div className="flex min-w-0 flex-1 items-center gap-3">
                            <Avatar src={req.avatar} label={label} />
                            <button
                              type="button"
                              className="min-w-0 flex-1 rounded-sm text-left outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              onClick={() => openTimeline(req.id, label)}
                              title="檢視授權紀錄"
                            >
                              <p className="text-sub font-medium truncate hover:underline">
                                {label}
                              </p>
                              <p className="text-label text-muted-foreground">
                                {formatDateTimeShort(req.created_at)} 提出申請
                              </p>
                            </button>
                          </div>
                          <div className="flex items-center gap-element self-end sm:self-auto">
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
                      )
                    })}
                  </div>
                )}
              </section>
            )}

            <section aria-labelledby="activation-grants-title" className="min-w-0 space-y-section">
              <div className="flex flex-col gap-element sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 id="activation-grants-title" className="text-sub font-semibold">
                    啟用碼
                  </h3>
                  <p className="text-label text-muted-foreground">依使用狀態檢視發放與兌換紀錄。</p>
                </div>
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
                    <Skeleton key={i} className="h-28 w-full rounded-lg" />
                  ))}
                </div>
              ) : grantsError ? (
                <ErrorState
                  message="啟用碼載入失敗"
                  actionLabel="重試啟用碼"
                  onRetry={retryGrants}
                />
              ) : grants.length === 0 ? (
                <EmptyState
                  icon="fa-solid fa-ticket"
                  title="沒有符合目前篩選條件的啟用碼"
                  description="切換上方狀態，或產生新的啟用碼。"
                />
              ) : (
                <div className="divide-y overflow-hidden rounded-lg border">
                  {grants.map(g => {
                    const label = g.display_name ?? g.username ?? g.platform_user_id ?? '尚未綁定'
                    const timeLabel =
                      g.status === 'issued' ? '到期時間' : g.used_at ? '使用時間' : '到期時間'
                    const timeValue = formatDateTimeShort(g.used_at ?? g.expires_at)
                    return (
                      <article
                        key={g.id}
                        aria-label={`${label} 的啟用碼`}
                        className="space-y-section px-3 py-3"
                      >
                        <div className="flex flex-col gap-section sm:flex-row sm:items-center sm:justify-between">
                          <div className="flex min-w-0 items-center gap-3">
                            <Avatar src={g.avatar} label={label} />
                            <div className="min-w-0">
                              <p className="text-sub font-medium truncate">{label}</p>
                              <p className="text-label text-muted-foreground font-mono truncate">
                                {g.username ?? g.platform_user_id ?? '尚未綁定帳號'}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-element self-end sm:self-auto">
                            <Badge
                              variant="outline"
                              className={`text-label ${STATUS_TONE[g.status]}`}
                            >
                              {STATUS_LABEL[g.status]}
                            </Badge>
                            {g.status === 'issued' && (
                              <Button
                                variant="ghost"
                                size="sm"
                                disabled={revoking === g.id}
                                onClick={() => handleRevoke(g.id)}
                                className="text-muted-foreground hover:text-destructive"
                                aria-label={`撤銷 ${label} 的啟用碼`}
                              >
                                <Icon
                                  icon={
                                    revoking === g.id
                                      ? 'fa-solid fa-spinner fa-spin'
                                      : 'fa-solid fa-ban'
                                  }
                                  size="xs"
                                />
                                撤銷
                              </Button>
                            )}
                          </div>
                        </div>

                        <dl className="grid grid-cols-2 gap-section border-t pt-section sm:grid-cols-3">
                          <GrantDatum label="來源">
                            <Badge variant="outline" className="text-label">
                              {KIND_LABEL[g.kind]}
                            </Badge>
                          </GrantDatum>
                          <GrantDatum label="啟用碼">
                            <span className="font-mono text-sub font-semibold tracking-wider">
                              {g.code_plain ?? '—'}
                            </span>
                          </GrantDatum>
                          <GrantDatum label={timeLabel}>
                            <span className="text-label tabular-nums text-muted-foreground">
                              {timeValue}
                              {g.reward_cost != null
                                ? ` · ${g.reward_cost.toLocaleString()} 點`
                                : ''}
                            </span>
                          </GrantDatum>
                        </dl>
                      </article>
                    )
                  })}
                </div>
              )}
            </section>
          </div>
        </CardContent>
      </Card>

      <Sheet open={!!timelineFor} onOpenChange={open => !open && setTimelineFor(null)}>
        <SheetContent className="sm:max-w-md">
          <SheetHeader>
            <SheetTitle>{timelineFor?.label} · 授權紀錄</SheetTitle>
          </SheetHeader>
          <div className="space-y-section overflow-y-auto px-4 pb-4">
            {timeline === null ? (
              <Spinner />
            ) : timeline.length === 0 ? (
              <p className="text-sub text-muted-foreground">沒有紀錄。</p>
            ) : (
              timeline.map(ev => (
                <article key={ev.id} className="space-y-element border-b pb-section last:border-0">
                  <div className="flex items-start justify-between gap-section">
                    <div className="flex items-center gap-element">
                      <span className="size-2 rounded-full bg-primary shrink-0" />
                      <p className="text-sub font-semibold">
                        {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                      </p>
                    </div>
                    <Badge variant="outline" className="text-label">
                      {ACTOR_LABEL[ev.actor_type]}
                    </Badge>
                  </div>
                  <time
                    dateTime={ev.occurred_at}
                    className="block text-label tabular-nums text-muted-foreground"
                  >
                    {formatDateTimeShort(ev.occurred_at)}
                  </time>
                  {ev.reason && (
                    <div className="rounded-md bg-muted px-3 py-2">
                      <p className="text-label font-medium text-muted-foreground">原因</p>
                      <p className="text-sub whitespace-pre-wrap break-words">{ev.reason}</p>
                    </div>
                  )}
                </article>
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

function Stat({ label, value, loading }: { label: string; value: string; loading: boolean }) {
  return (
    <div className="min-w-0 bg-card px-3 py-3 sm:px-4">
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className="mt-1 text-card-title font-bold tabular-nums">
        {loading ? <Skeleton className="h-5 w-10" /> : value}
      </dd>
    </div>
  )
}

function ErrorState({
  message,
  actionLabel,
  onRetry,
}: {
  message: string
  actionLabel: string
  onRetry: () => void
}) {
  return (
    <div
      role="alert"
      className="flex flex-col gap-element rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-3 sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-center gap-element text-destructive">
        <Icon icon="fa-solid fa-triangle-exclamation" size="xs" />
        <p className="text-sub font-medium">{message}</p>
      </div>
      <Button variant="outline" size="sm" onClick={onRetry} className="self-start sm:self-auto">
        <Icon icon="fa-solid fa-rotate" size="xs" />
        {actionLabel}
      </Button>
    </div>
  )
}

function GrantDatum({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0 space-y-1">
      <dt className="text-label text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
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
