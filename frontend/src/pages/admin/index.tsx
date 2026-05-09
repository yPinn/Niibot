import { useCallback, useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  type ActivationRequest,
  type AdminChannel,
  approveActivationRequest,
  getActivationRequests,
  getAdminChannels,
  type ModStatus,
  rejectActivationRequest,
} from '@/api/admin'
import {
  getRedemptionConfigs,
  getTwitchRewards,
  type RedemptionConfig,
  type TwitchReward,
  updateRedemptionConfig,
} from '@/api/events'
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
  CardDescription,
  CardHeader,
  CardTitle,
  Icon,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Skeleton,
  SlideUp,
  Spinner,
  Switch,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'

// ── Channels panel ────────────────────────────────────────────────────────────

const MOD_STATUS_CONFIG: Record<ModStatus, { label: string; icon: string; className: string }> = {
  mod: {
    label: 'mod',
    icon: 'fa-solid fa-shield-check',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  no_mod: {
    label: 'no mod',
    icon: 'fa-solid fa-shield-xmark',
    className: 'border-status-offline/20 bg-status-offline/10 text-status-offline',
  },
  token_error: {
    label: 'token expired',
    icon: 'fa-solid fa-rotate-exclamation',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
  scope_error: {
    label: 'scope outdated',
    icon: 'fa-solid fa-lock',
    className: 'border-status-info/20 bg-status-info/10 text-status-info',
  },
}

function ModStatusBadge({ status }: { status: ModStatus }) {
  const cfg = MOD_STATUS_CONFIG[status] ?? MOD_STATUS_CONFIG.token_error
  return (
    <Badge className={`gap-1 text-label ${cfg.className}`}>
      <Icon icon={cfg.icon} size="xs" />
      {cfg.label}
    </Badge>
  )
}

function ChannelRow({ ch }: { ch: AdminChannel }) {
  return (
    <div className="flex items-center gap-3 py-2">
      <img
        src={ch.avatar}
        alt={ch.display_name}
        className="size-7 rounded-full shrink-0 object-cover"
      />
      <div className="flex-1 min-w-0">
        <p className="text-sub font-medium truncate">{ch.display_name}</p>
        <p className="text-label text-muted-foreground font-mono truncate">{ch.name}</p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {ch.is_live && (
          <Badge className="border-status-live/20 bg-status-live/10 text-status-live gap-1 text-label">
            <Icon icon="fa-solid fa-circle" size="xs" />
            LIVE
          </Badge>
        )}
        <ModStatusBadge status={ch.mod_status} />
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  useDocumentTitle('Admin')

  // ── Channels ──
  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)

  // ── Niibot auth redemption ──
  const [niibotAuth, setNiibotAuth] = useState<RedemptionConfig | null>(null)
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)

  // ── Activation requests ──
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [requestsLoading, setRequestsLoading] = useState(true)
  const [actioningId, setActioningId] = useState<number | null>(null)
  const [confirmReject, setConfirmReject] = useState<ActivationRequest | null>(null)

  useEffect(() => {
    getAdminChannels()
      .then(setChannels)
      .catch(() => setChannels([]))
      .finally(() => setChannelsLoading(false))

    getRedemptionConfigs()
      .then(configs => setNiibotAuth(configs.find(r => r.action_type === 'niibot_auth') ?? null))
      .catch(() => setNiibotAuth(null))
      .finally(() => setRedemptionLoading(false))

    getTwitchRewards()
      .then(rewards => setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost)))
      .catch(() => setTwitchRewards([]))
      .finally(() => setRewardsLoading(false))

    getActivationRequests()
      .then(data => setRequests(data))
      .catch(() => setRequests([]))
      .finally(() => setRequestsLoading(false))
  }, [])

  const fetchRequests = useCallback(async () => {
    setRequestsLoading(true)
    try {
      const data = await getActivationRequests()
      setRequests(data)
    } catch {
      setRequests([])
    } finally {
      setRequestsLoading(false)
    }
  }, [])

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

  const handleRewardSelect = async (rewardTitle: string) => {
    if (!niibotAuth) return
    try {
      const updated = await updateRedemptionConfig('niibot_auth', {
        reward_name: rewardTitle === '__none__' ? '' : rewardTitle,
        enabled: niibotAuth.enabled,
      })
      setNiibotAuth(updated)
      toast.success('Niibot 授權獎勵已更新')
    } catch {
      toast.error('更新失敗')
    }
  }

  const handleAuthToggle = async () => {
    if (!niibotAuth) return
    const newEnabled = !niibotAuth.enabled
    setNiibotAuth(prev => (prev ? { ...prev, enabled: newEnabled } : prev))
    try {
      const updated = await updateRedemptionConfig('niibot_auth', {
        reward_name: niibotAuth.reward_name,
        enabled: newEnabled,
      })
      setNiibotAuth(updated)
    } catch {
      setNiibotAuth(prev => (prev ? { ...prev, enabled: !newEnabled } : prev))
      toast.error('切換狀態失敗')
    }
  }

  return (
    <PageMain className="lg:gap-card">
      <PageHeader title="Admin" />

      {/* Activation requests */}
      <SlideUp>
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
                  onClick={() => {
                    setRequestsLoading(true)
                    void fetchRequests()
                  }}
                  aria-label="Refresh"
                >
                  <Icon icon="fa-solid fa-rotate" wrapperClassName="text-muted-foreground" />
                </Button>
              </div>
            </CardAction>
          </CardHeader>
          <CardContent>
            {requestsLoading ? (
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
      </SlideUp>

      {/* Niibot auth redemption */}
      <SlideUp>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Icon icon="fa-solid fa-coins" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">Niibot 授權兌換</CardTitle>
            </div>
            <CardDescription>指定觀眾兌換後取得 Niibot 啟用碼的頻道點數獎勵</CardDescription>
          </CardHeader>
          <CardContent>
            {redemptionLoading ? (
              <Skeleton className="h-10 w-full" />
            ) : !niibotAuth ? (
              <p className="text-sub text-muted-foreground py-2">找不到 niibot_auth 兌換設定。</p>
            ) : (
              <div className="flex flex-wrap items-center gap-4">
                {rewardsLoading ? (
                  <Skeleton className="h-9 w-52" />
                ) : twitchRewards.length === 0 ? (
                  <span className="text-sub text-muted-foreground">請先在 Twitch 建立自訂獎勵</span>
                ) : (
                  <Select
                    value={niibotAuth.reward_name || '__none__'}
                    onValueChange={handleRewardSelect}
                  >
                    <SelectTrigger size="sm" className="w-52">
                      <SelectValue placeholder="選擇獎勵..." />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__none__" className="text-muted-foreground">
                        未選擇
                      </SelectItem>
                      {twitchRewards.map(reward => (
                        <SelectItem key={reward.id} value={reward.title}>
                          {reward.title} ({reward.cost.toLocaleString()} 點)
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
                <div className="flex items-center gap-2 ml-auto">
                  <span className="text-sub text-muted-foreground">啟用</span>
                  <Switch checked={niibotAuth.enabled} onCheckedChange={handleAuthToggle} />
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      {/* Channels */}
      <SlideUp>
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Icon icon="fa-brands fa-twitch" size="sm" wrapperClassName="text-muted-foreground" />
              <CardTitle className="text-card-title">Monitored Channels</CardTitle>
            </div>
            <CardAction>
              <Badge variant="outline" className="font-mono text-label">
                {channelsLoading ? '…' : channels.length}
              </Badge>
            </CardAction>
          </CardHeader>
          <CardContent>
            {channelsLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : channels.length === 0 ? (
              <p className="text-sub text-muted-foreground py-2">No monitored channels.</p>
            ) : (
              channels.map((ch, idx) => (
                <div key={ch.id}>
                  {idx > 0 && <Separator className="opacity-40" />}
                  <ChannelRow ch={ch} />
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </SlideUp>

      {/* Reject confirmation dialog */}
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
    </PageMain>
  )
}
