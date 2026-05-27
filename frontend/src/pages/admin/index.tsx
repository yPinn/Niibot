import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  type ActivationRequest,
  type AdminChannel,
  approveActivationRequest,
  type BotTokenInfo,
  getActivationRequests,
  getAdminBotStatus,
  getAdminChannels,
  getPendingActivationCodes,
  type ModStatus,
  type PendingCode,
  rejectActivationRequest,
  revokeActivationCode,
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
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
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
  TwitchRoleBadge,
  TwitchRoleBadgeLabel,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { formatDateTimeShort } from '@/lib/format'

// ── Scope grouping ────────────────────────────────────────────────────────────

const SCOPE_CATEGORIES: { label: string; scopes: string[] }[] = [
  { label: 'Identity', scopes: ['user:bot', 'channel:bot'] },
  { label: 'Chat', scopes: ['user:read:chat', 'user:write:chat'] },
  { label: 'User', scopes: ['user:read:emotes', 'user:manage:whispers'] },
  {
    label: 'Channel',
    scopes: [
      'channel:read:redemptions',
      'channel:read:subscriptions',
      'channel:manage:moderators',
      'channel:manage:vips',
    ],
  },
  { label: 'Revenue', scopes: ['bits:read'] },
  {
    label: 'Moderation',
    scopes: [
      'moderation:read',
      'moderator:read:followers',
      'moderator:read:chatters',
      'moderator:manage:announcements',
      'moderator:manage:shoutouts',
    ],
  },
]

function buildScopeGroups(granted: string[], missing: string[]) {
  const grantedSet = new Set(granted)
  const allSet = new Set([...granted, ...missing])
  const matched = new Set<string>()
  const groups: { label: string; items: { scope: string; granted: boolean }[] }[] = []

  for (const cat of SCOPE_CATEGORIES) {
    const inCat = cat.scopes.filter(s => allSet.has(s))
    if (inCat.length === 0) continue
    inCat.forEach(s => matched.add(s))
    groups.push({
      label: cat.label,
      items: [
        ...inCat.filter(s => !grantedSet.has(s)).map(s => ({ scope: s, granted: false })),
        ...inCat.filter(s => grantedSet.has(s)).map(s => ({ scope: s, granted: true })),
      ],
    })
  }

  const others = [...allSet].filter(s => !matched.has(s))
  if (others.length > 0) {
    groups.push({
      label: 'Other',
      items: others.map(s => ({ scope: s, granted: grantedSet.has(s) })),
    })
  }

  return groups
}

// ── Scope display ─────────────────────────────────────────────────────────────

function ScopeRow({ scope, granted }: { scope: string; granted: boolean }) {
  return (
    <div className="flex items-center gap-element py-0.5">
      <Icon
        icon={granted ? 'fa-solid fa-check' : 'fa-solid fa-xmark'}
        size="xs"
        className={granted ? 'text-status-online shrink-0' : 'text-status-offline shrink-0'}
      />
      <code className={`text-label font-mono ${granted ? 'text-muted-foreground' : ''}`}>
        {scope}
      </code>
    </div>
  )
}

function ScopeSection({
  title,
  granted,
  missing,
}: {
  title?: string
  granted: string[]
  missing: string[]
}) {
  const groups = buildScopeGroups(granted, missing)
  return (
    <div className="space-y-element">
      {title && (
        <p className="text-label font-medium uppercase tracking-wide text-muted-foreground">
          {title}
        </p>
      )}
      <div className="rounded-md border border-border bg-muted p-3">
        {groups.length === 0 ? (
          <p className="text-label text-muted-foreground">No scope data stored</p>
        ) : (
          <div>
            {groups.map((group, i) => (
              <div key={group.label}>
                {i > 0 && <div className="border-t border-border my-1.5" />}
                {group.items.map(({ scope, granted: g }) => (
                  <ScopeRow key={scope} scope={scope} granted={g} />
                ))}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Mod status badge ──────────────────────────────────────────────────────────

const MOD_STATUS_CONFIG: Record<
  ModStatus,
  { label: string; labelZh: string; icon: string; iconClass: string; className: string }
> = {
  mod: {
    label: 'mod',
    labelZh: '管理員',
    icon: 'fa-solid fa-shield-check',
    iconClass: 'text-status-online',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  no_mod: {
    label: 'no mod',
    labelZh: '非管理員',
    icon: 'fa-solid fa-shield-xmark',
    iconClass: 'text-status-offline',
    className: 'border-status-offline/20 bg-status-offline/10 text-status-offline',
  },
  token_error: {
    label: 'expired',
    labelZh: 'Token 過期',
    icon: 'fa-solid fa-rotate-exclamation',
    iconClass: 'text-status-warning',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
  scope_error: {
    label: 'scope outdated',
    labelZh: '授權不足',
    icon: 'fa-solid fa-lock',
    iconClass: 'text-status-info',
    className: 'border-status-info/20 bg-status-info/10 text-status-info',
  },
  broadcaster: {
    label: 'broadcaster',
    labelZh: '轉播者',
    icon: '',
    iconClass: 'text-muted-foreground',
    className: 'border-border bg-muted/50 text-muted-foreground',
  },
}

function ModStatusBadge({
  status,
  missingCount,
  bare,
}: {
  status: ModStatus
  missingCount?: number
  bare?: boolean
}) {
  const cfg = MOD_STATUS_CONFIG[status] ?? MOD_STATUS_CONFIG.token_error

  const icon =
    status === 'mod' ? (
      <TwitchRoleBadge role="moderator" size={18} />
    ) : status === 'broadcaster' ? (
      <TwitchRoleBadge role="broadcaster" size={18} />
    ) : (
      <Icon
        icon={cfg.icon}
        size={bare ? 'badge' : 'xs'}
        wrapperClassName={bare ? `shrink-0 ${cfg.iconClass}` : undefined}
      />
    )

  if (bare) {
    const label =
      status === 'scope_error' && missingCount != null ? `${missingCount} 個授權遺失` : cfg.labelZh
    return (
      <span className="inline-flex items-center gap-1.5 select-none">
        {icon}
        <span className="text-sub text-foreground">{label}</span>
      </span>
    )
  }

  const label =
    status === 'broadcaster'
      ? null
      : status === 'scope_error' && missingCount != null
        ? `${missingCount} missing`
        : cfg.label
  return (
    <Badge className={`gap-1 text-label select-none ${cfg.className}`}>
      {icon}
      {label}
    </Badge>
  )
}

// ── Scope detail dialog ───────────────────────────────────────────────────────

function ScopeDetailDialog({
  ch,
  open,
  onOpenChange,
}: {
  ch: AdminChannel
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <div className="flex items-center gap-element">
            <img
              src={ch.avatar}
              alt={ch.display_name}
              className="size-9 rounded-full object-cover shrink-0"
            />
            <div className="min-w-0">
              <DialogTitle>{ch.display_name}</DialogTitle>
              <DialogDescription className="font-mono">{ch.name}</DialogDescription>
            </div>
          </div>
          <div className="flex flex-col gap-element mt-1">
            <TwitchRoleBadgeLabel role="bot" />
            <ModStatusBadge
              status={ch.is_bot ? 'broadcaster' : ch.mod_status}
              missingCount={ch.missing_scopes.length}
              bare
            />
          </div>
        </DialogHeader>
        <ScopeSection
          title="Broadcaster Scopes"
          granted={ch.granted_scopes}
          missing={ch.missing_scopes}
        />
      </DialogContent>
    </Dialog>
  )
}

// ── Channel card ──────────────────────────────────────────────────────────────

function ModStatusIcon({ status }: { status: ModStatus }) {
  if (status === 'broadcaster')
    return <TwitchRoleBadge role="broadcaster" size={18} className="drop-shadow-sm" />
  if (status === 'mod')
    return <TwitchRoleBadge role="moderator" size={18} className="drop-shadow-sm" />
  const cfg = MOD_STATUS_CONFIG[status]
  return (
    <span className={`inline-flex items-center justify-center size-4.5 rounded ${cfg.className}`}>
      <Icon icon={cfg.icon} size="badge" />
    </span>
  )
}

function PauseStatusIcon() {
  return (
    <span className="inline-flex items-center justify-center size-4.5 rounded border-border bg-muted/80 text-muted-foreground">
      <Icon icon="fa-solid fa-circle-pause" size="badge" />
    </span>
  )
}

function ChannelCard({ ch }: { ch: AdminChannel }) {
  const [open, setOpen] = useState(false)
  const status: ModStatus = ch.is_bot ? 'broadcaster' : ch.mod_status
  const isPaused = !ch.is_enabled

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`relative w-full aspect-video rounded-lg border border-border overflow-hidden hover:ring-2 hover:ring-primary transition-all select-none${isPaused ? ' opacity-50 grayscale' : ''}`}
      >
        {ch.offline_image_url ? (
          <img
            src={ch.offline_image_url}
            alt=""
            className="absolute inset-0 size-full object-cover"
          />
        ) : (
          <div className="absolute inset-0 bg-muted" />
        )}

        <div className="absolute inset-0 bg-linear-to-t from-black via-black/60 to-black/25" />
        <div className="absolute top-0 right-0 w-16 h-9 bg-black/90 rounded-bl-full" />

        <div className="absolute top-2 right-2 flex items-center gap-1">
          <TwitchRoleBadge role="bot" size={18} className="drop-shadow-sm opacity-80" />
          {isPaused ? <PauseStatusIcon /> : <ModStatusIcon status={status} />}
        </div>

        <div className="absolute bottom-0 left-0 right-0 flex items-end gap-2 p-2.5">
          <img
            src={ch.avatar}
            alt={ch.display_name}
            className="size-8 rounded-full object-cover border-2 border-white/20 shrink-0"
          />
          <div className="flex-1 min-w-0 text-left">
            <p className="text-sub font-semibold text-white truncate leading-tight">
              {ch.display_name}
            </p>
            <p className="text-label text-white/60 font-mono truncate">{ch.name}</p>
          </div>
          {ch.is_live && <span className="size-2 rounded-full bg-status-live shrink-0 mb-1" />}
        </div>
      </button>
      <ScopeDetailDialog ch={ch} open={open} onOpenChange={setOpen} />
    </>
  )
}

// ── Bot status panel ──────────────────────────────────────────────────────────

const BOT_STATUS_CONFIG = {
  ok: {
    label: 'All scopes granted',
    icon: 'fa-solid fa-shield-check',
    textClass: 'text-status-online',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  },
  missing: {
    label: 'scopes missing',
    icon: 'fa-solid fa-lock',
    textClass: 'text-status-info',
    className: 'border-status-info/20 bg-status-info/10 text-status-info',
  },
  no_token: {
    label: 'No bot token',
    icon: 'fa-solid fa-rotate-exclamation',
    textClass: 'text-status-warning',
    className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
  },
}

function BotStatusPanel({
  bot,
  botLoading,
  redemptionLoading,
  rewardsLoading,
  niibotAuth,
  twitchRewards,
  onRewardSelect,
  onAuthToggle,
}: {
  bot: BotTokenInfo | null
  botLoading: boolean
  redemptionLoading: boolean
  rewardsLoading: boolean
  niibotAuth: RedemptionConfig | null
  twitchRewards: TwitchReward[]
  onRewardSelect: (value: string) => void
  onAuthToggle: () => void
}) {
  const botCfg = bot ? BOT_STATUS_CONFIG[bot.status] : null

  return (
    <Card className="lg:h-full">
      <CardHeader>
        <div className="flex items-center gap-element">
          <Icon icon="fa-solid fa-robot" size="sm" wrapperClassName="text-muted-foreground" />
          <CardTitle className="text-card-title">Bot 設定</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-section">
        {botLoading ? (
          <>
            <div className="flex items-center gap-element rounded-md border border-border px-2 py-1.5">
              <Skeleton className="size-8 rounded-full shrink-0" />
              <div className="flex-1 space-y-1">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="size-4.5 rounded shrink-0" />
            </div>
            <Skeleton className="h-40 w-full rounded-md" />
          </>
        ) : bot && botCfg ? (
          <>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className="flex items-center gap-element w-full rounded-md border border-border px-2 py-1.5 hover:bg-accent transition-colors text-left select-none"
                >
                  {bot.avatar && (
                    <img
                      src={bot.avatar}
                      alt={bot.display_name || bot.name}
                      className="size-8 rounded-full object-cover shrink-0"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <TwitchRoleBadge role="bot" size={18} className="shrink-0 opacity-80" />
                      <p className="text-sub font-medium truncate">
                        {bot.display_name || bot.name}
                      </p>
                    </div>
                    <p className="text-label text-muted-foreground font-mono truncate">
                      {bot.name}
                    </p>
                  </div>
                  <Icon
                    icon="fa-solid fa-chevron-down"
                    size="badge"
                    wrapperClassName="text-muted-foreground/60 shrink-0"
                  />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                align="start"
                style={{ width: 'var(--radix-dropdown-menu-trigger-width)' }}
              >
                <DropdownMenuLabel className="font-normal">
                  <div className="flex items-center gap-element">
                    {bot.avatar && (
                      <img src={bot.avatar} alt="" className="size-6 rounded-full shrink-0" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-sub font-medium truncate">
                        {bot.display_name || bot.name}
                      </p>
                      <p className="text-label text-muted-foreground font-mono truncate">
                        {bot.name}
                      </p>
                    </div>
                    <Icon
                      icon={botCfg.icon}
                      size="badge"
                      className={`shrink-0 ${botCfg.textClass}`}
                    />
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem disabled className="text-muted-foreground/50 gap-element">
                  <Icon icon="fa-solid fa-plus" size="xs" />
                  新增帳號（尚未支援）
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <ScopeSection granted={bot.granted_scopes} missing={bot.missing_scopes} />
          </>
        ) : null}

        <Separator />

        <div className="space-y-element">
          <div className="flex items-center gap-element">
            <Icon icon="fa-solid fa-coins" size="xs" wrapperClassName="text-muted-foreground" />
            <p className="text-label font-medium text-muted-foreground select-none">授權兌換</p>
          </div>
          {redemptionLoading ? (
            <Skeleton className="h-9 w-full" />
          ) : !niibotAuth ? (
            <p className="text-label text-muted-foreground">找不到 niibot_auth 兌換設定。</p>
          ) : (
            <div className="flex items-center justify-between gap-element">
              {rewardsLoading ? (
                <Skeleton className="h-9 flex-1" />
              ) : twitchRewards.length === 0 ? (
                <span className="text-label text-muted-foreground">請先在 Twitch 建立自訂獎勵</span>
              ) : (
                <Select value={niibotAuth.reward_name || '__none__'} onValueChange={onRewardSelect}>
                  <SelectTrigger size="sm" className="flex-1 min-w-0">
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
              <Switch checked={niibotAuth.enabled} onCheckedChange={onAuthToggle} />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

// ── Activation card (requests + codes) ───────────────────────────────────────

function ActivationCard() {
  const [requests, setRequests] = useState<ActivationRequest[]>([])
  const [reqLoading, setReqLoading] = useState(true)
  const [actioningId, setActioningId] = useState<number | null>(null)
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
    } catch {
      toast.error('撤銷失敗')
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

// ── Page ──────────────────────────────────────────────────────────────────────

export default function AdminPage() {
  useDocumentTitle('Admin')

  const [channels, setChannels] = useState<AdminChannel[]>([])
  const [channelsLoading, setChannelsLoading] = useState(true)

  const { healthyChannels, issueChannels, pausedChannels } = useMemo(() => {
    const sortByLive = (chs: AdminChannel[]) =>
      [...chs].sort((a, b) => (b.is_live ? 1 : 0) - (a.is_live ? 1 : 0))
    const nonBots = channels.filter(ch => !ch.is_bot)
    const active = nonBots.filter(ch => ch.is_enabled)
    const paused = nonBots.filter(ch => !ch.is_enabled)
    return {
      healthyChannels: sortByLive(
        active.filter(ch => ch.mod_status === 'mod' && ch.missing_scopes.length === 0)
      ),
      issueChannels: sortByLive(
        active.filter(ch => ch.mod_status !== 'mod' || ch.missing_scopes.length > 0)
      ),
      pausedChannels: sortByLive(paused),
    }
  }, [channels])

  const [botStatus, setBotStatus] = useState<BotTokenInfo | null>(null)
  const [botLoading, setBotLoading] = useState(true)

  const [niibotAuth, setNiibotAuth] = useState<RedemptionConfig | null>(null)
  const [twitchRewards, setTwitchRewards] = useState<TwitchReward[]>([])
  const [redemptionLoading, setRedemptionLoading] = useState(true)
  const [rewardsLoading, setRewardsLoading] = useState(true)

  useEffect(() => {
    getAdminChannels()
      .then(setChannels)
      .catch(() => setChannels([]))
      .finally(() => setChannelsLoading(false))

    getAdminBotStatus()
      .then(setBotStatus)
      .catch(() => setBotStatus(null))
      .finally(() => setBotLoading(false))

    getRedemptionConfigs()
      .then(configs => setNiibotAuth(configs.find(r => r.action_type === 'niibot_auth') ?? null))
      .catch(() => setNiibotAuth(null))
      .finally(() => setRedemptionLoading(false))

    getTwitchRewards()
      .then(rewards => setTwitchRewards([...rewards].sort((a, b) => a.cost - b.cost)))
      .catch(() => setTwitchRewards([]))
      .finally(() => setRewardsLoading(false))
  }, [])

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
      <PageHeader title="Admin" description="管理頻道點數兌換與監控頻道。" />

      <div className="grid grid-cols-1 gap-card items-start lg:grid-cols-[1fr_360px]">
        <SlideUp>
          <Card>
            <CardHeader>
              <div className="flex items-center gap-element">
                <Icon
                  icon="fa-brands fa-twitch"
                  size="sm"
                  wrapperClassName="text-muted-foreground"
                />
                <CardTitle className="text-card-title">監控頻道</CardTitle>
              </div>
              <CardAction>
                <Badge variant="outline" className="font-mono text-label">
                  {channelsLoading ? '…' : channels.length}
                </Badge>
              </CardAction>
            </CardHeader>
            <CardContent>
              {channelsLoading ? (
                <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                  {Array.from({ length: 8 }).map((_, i) => (
                    <Skeleton key={i} className="w-full aspect-video rounded-lg" />
                  ))}
                </div>
              ) : channels.length === 0 ? (
                <p className="text-sub text-muted-foreground py-2">No monitored channels.</p>
              ) : (
                <div className="space-y-section">
                  {issueChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-status-warning select-none">
                          需注意
                        </span>
                        <Badge className="border-status-warning/20 bg-status-warning/10 text-status-warning font-mono text-label">
                          {issueChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {issueChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} />
                        ))}
                      </div>
                    </div>
                  )}
                  <div>
                    {issueChannels.length > 0 && (
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                          正常
                        </span>
                        <Badge variant="outline" className="font-mono text-label">
                          {healthyChannels.length}
                        </Badge>
                      </div>
                    )}
                    <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                      {healthyChannels.map(ch => (
                        <ChannelCard key={ch.id} ch={ch} />
                      ))}
                    </div>
                  </div>

                  {pausedChannels.length > 0 && (
                    <div>
                      <div className="flex items-center gap-element mb-section">
                        <span className="text-label font-medium uppercase tracking-wide text-muted-foreground select-none">
                          暫停中
                        </span>
                        <Badge variant="outline" className="font-mono text-label">
                          {pausedChannels.length}
                        </Badge>
                      </div>
                      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(200px,1fr))]">
                        {pausedChannels.map(ch => (
                          <ChannelCard key={ch.id} ch={ch} />
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </SlideUp>

        <SlideUp delay={0.1}>
          <div className="space-y-card">
            <BotStatusPanel
              bot={botStatus}
              botLoading={botLoading}
              redemptionLoading={redemptionLoading}
              rewardsLoading={rewardsLoading}
              niibotAuth={niibotAuth}
              twitchRewards={twitchRewards}
              onRewardSelect={handleRewardSelect}
              onAuthToggle={handleAuthToggle}
            />
            <ActivationCard />
          </div>
        </SlideUp>
      </div>
    </PageMain>
  )
}
