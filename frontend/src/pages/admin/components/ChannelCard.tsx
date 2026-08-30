import { useState } from 'react'

import type { AdminChannel, ModStatus } from '@/api/admin'
import { Icon, Spinner, TwitchRoleBadge } from '@/components/primitives'
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@/components/ui'

import { ScopeSection } from './ScopeSection'

// ── Mod status config ─────────────────────────────────────────────────────────

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

export function ModStatusBadge({
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

// ── Membership status config ────────────────────────────────────────────────

const MEMBERSHIP_STATUS_LABEL: Record<'pending' | 'suspended', string> = {
  pending: '待審核中，尚未通過授權',
  suspended: '使用者已停權，bot 已停止監控此頻道',
}

const SUSPENSION_REASON_PRESETS = [
  '違反使用規範',
  '濫用或惡意操作',
  '帳號安全風險',
  '管理員人工審查',
] as const

interface ChannelStatusPresentation {
  label: string
  icon: string
  className: string
}

function getMembershipStatus(ch: AdminChannel): ChannelStatusPresentation {
  if (ch.membership_status === 'suspended') {
    return {
      label: '已停權',
      icon: 'fa-solid fa-ban',
      className: 'border-destructive/20 bg-destructive/10 text-destructive',
    }
  }
  if (ch.membership_status === 'pending') {
    return {
      label: '待審核',
      icon: 'fa-solid fa-hourglass-half',
      className: 'border-status-info/20 bg-status-info/10 text-status-info',
    }
  }
  return {
    label: '使用中',
    icon: 'fa-solid fa-user-check',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  }
}

function getMonitoringStatus(ch: AdminChannel): ChannelStatusPresentation {
  if (ch.membership_status === 'suspended') {
    return {
      label: '監控已停止',
      icon: 'fa-solid fa-circle-stop',
      className: 'border-destructive/20 bg-destructive/10 text-destructive',
    }
  }
  if (ch.membership_status === 'pending') {
    return {
      label: '尚未啟用',
      icon: 'fa-solid fa-clock',
      className: 'border-border bg-muted text-muted-foreground',
    }
  }
  if (!ch.is_enabled) {
    return {
      label: '監控暫停',
      icon: 'fa-solid fa-circle-pause',
      className: 'border-border bg-muted text-muted-foreground',
    }
  }
  if (ch.missing_scopes.length > 0 || ch.mod_status === 'scope_error') {
    const count = ch.missing_scopes.length
    return {
      label: count > 0 ? `缺少 ${count} 項權限` : '授權不足',
      icon: 'fa-solid fa-lock',
      className: 'border-status-info/20 bg-status-info/10 text-status-info',
    }
  }
  if (ch.mod_status === 'token_error') {
    return {
      label: 'Token 過期',
      icon: 'fa-solid fa-rotate-exclamation',
      className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
    }
  }
  if (ch.mod_status === 'no_mod') {
    return {
      label: 'Bot 非管理員',
      icon: 'fa-solid fa-shield-xmark',
      className: 'border-status-offline/20 bg-status-offline/10 text-status-offline',
    }
  }
  return {
    label: '監控正常',
    icon: 'fa-solid fa-shield-check',
    className: 'border-status-online/20 bg-status-online/10 text-status-online',
  }
}

function ChannelStatusBadges({ ch, media = false }: { ch: AdminChannel; media?: boolean }) {
  const membership = getMembershipStatus(ch)
  const monitoring = getMonitoringStatus(ch)

  return (
    <div className="flex flex-wrap items-center gap-element">
      {[membership, monitoring].map(item => (
        <Badge
          key={item.label}
          className={`gap-1 text-label ${media ? 'shadow-sm backdrop-blur-sm' : ''} ${item.className}`}
        >
          <Icon icon={item.icon} size="badge" />
          {item.label}
        </Badge>
      ))}
    </div>
  )
}

// ── Scope detail dialog ───────────────────────────────────────────────────────

function ScopeDetailDialog({
  ch,
  open,
  onOpenChange,
  onSuspendRequest,
  onReinstate,
}: {
  ch: AdminChannel
  open: boolean
  onOpenChange: (v: boolean) => void
  onSuspendRequest?: () => void
  onReinstate?: (ch: AdminChannel) => void | Promise<void>
}) {
  const [reinstating, setReinstating] = useState(false)

  const handleReinstate = async () => {
    if (!onReinstate) return
    setReinstating(true)
    try {
      await onReinstate(ch)
      onOpenChange(false)
    } finally {
      setReinstating(false)
    }
  }

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
          <div className="mt-1 space-y-element">
            <ChannelStatusBadges ch={ch} />
            {(ch.membership_status === 'pending' || ch.membership_status === 'suspended') && (
              <p className="text-label text-muted-foreground">
                {MEMBERSHIP_STATUS_LABEL[ch.membership_status]}
              </p>
            )}
          </div>
        </DialogHeader>
        {ch.membership_status !== 'suspended' && (
          <ScopeSection
            title="Broadcaster Scopes"
            granted={ch.granted_scopes}
            missing={ch.missing_scopes}
          />
        )}
        {ch.membership_status === 'suspended' && ch.membership_reason && (
          <div className="space-y-element rounded-md bg-muted p-3">
            <p className="text-label font-medium text-muted-foreground">停權原因</p>
            <p className="text-sub whitespace-pre-wrap break-words">{ch.membership_reason}</p>
          </div>
        )}
        {ch.membership_status === 'active' && onSuspendRequest && (
          <Button
            variant="outline"
            className="text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
            onClick={() => {
              onOpenChange(false)
              onSuspendRequest()
            }}
          >
            <Icon icon="fa-solid fa-ban" size="xs" />
            停權使用者
          </Button>
        )}
        {ch.membership_status === 'suspended' && onReinstate && (
          <Button
            variant="outline"
            className="text-status-online border-status-online/30 hover:bg-status-online/10"
            onClick={() => void handleReinstate()}
            disabled={reinstating}
          >
            {reinstating ? <Spinner /> : <Icon icon="fa-solid fa-rotate-left" size="xs" />}
            恢復授權
          </Button>
        )}
      </DialogContent>
    </Dialog>
  )
}

function SuspendMembershipDialog({
  ch,
  open,
  onOpenChange,
  onSuspend,
}: {
  ch: AdminChannel
  open: boolean
  onOpenChange: (v: boolean) => void
  onSuspend: (ch: AdminChannel, reason: string) => Promise<boolean>
}) {
  const [preset, setPreset] = useState('')
  const [reason, setReason] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const trimmedReason = reason.trim()

  const reset = () => {
    setPreset('')
    setReason('')
  }

  const handleOpenChange = (nextOpen: boolean) => {
    if (!nextOpen && !submitting) reset()
    onOpenChange(nextOpen)
  }

  const handleSuspend = async () => {
    if (!trimmedReason) return
    setSubmitting(true)
    try {
      if (await onSuspend(ch, trimmedReason)) {
        reset()
        onOpenChange(false)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>停權 {ch.display_name}</DialogTitle>
          <DialogDescription>
            停權後，使用者將無法使用產品功能，bot
            也會立即停止監控此頻道。既有資料會保留，且只有管理員能恢復授權。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-section">
          <div className="space-y-element">
            <Label>常見原因</Label>
            <Select
              value={preset}
              onValueChange={value => {
                setPreset(value)
                setReason(value)
              }}
              disabled={submitting}
            >
              <SelectTrigger className="w-full" aria-label="常見原因">
                <SelectValue placeholder="選擇常見原因以快速帶入" />
              </SelectTrigger>
              <SelectContent>
                {SUSPENSION_REASON_PRESETS.map(item => (
                  <SelectItem key={item} value={item}>
                    {item}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-element">
            <div className="flex items-center justify-between gap-element">
              <Label htmlFor={`suspension-reason-${ch.id}`}>停權原因</Label>
              <span className="text-label tabular-nums text-muted-foreground">
                {reason.length}/500
              </span>
            </div>
            <Textarea
              id={`suspension-reason-${ch.id}`}
              value={reason}
              onChange={event => setReason(event.target.value)}
              maxLength={500}
              placeholder="選擇常見原因，或輸入具體原因"
              disabled={submitting}
              autoFocus
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button
            variant="destructive"
            onClick={() => void handleSuspend()}
            disabled={!trimmedReason || submitting}
          >
            {submitting ? <Spinner /> : <Icon icon="fa-solid fa-ban" size="xs" />}
            確認停權
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Channel card ──────────────────────────────────────────────────────────────

export function ChannelCard({
  ch,
  onSuspend,
  onReinstate,
}: {
  ch: AdminChannel
  onSuspend?: (ch: AdminChannel, reason: string) => Promise<boolean>
  onReinstate?: (ch: AdminChannel) => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [suspendOpen, setSuspendOpen] = useState(false)
  const isSuspended = ch.membership_status === 'suspended'
  const isDimmed = !ch.is_enabled || ch.membership_status !== 'active'
  const membership = getMembershipStatus(ch)
  const monitoring = getMonitoringStatus(ch)

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`${ch.display_name}，${membership.label}，${monitoring.label}`}
        className="group relative aspect-video w-full overflow-hidden rounded-lg border border-border text-left transition-[border-color,box-shadow] hover:border-primary/40 hover:ring-2 hover:ring-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring select-none"
      >
        {ch.offline_image_url ? (
          <img
            src={ch.offline_image_url}
            alt=""
            className={`absolute inset-0 size-full object-cover transition-[filter,opacity] ${isDimmed ? 'opacity-50 grayscale' : ''}`}
          />
        ) : (
          <div className="absolute inset-0 bg-muted" />
        )}

        <div className="absolute inset-0 bg-linear-to-t from-black via-black/60 to-black/25" />
        <div className="absolute top-0 right-0 h-9 w-16 rounded-bl-full bg-black/90" />

        <div className="absolute top-2 left-2 right-11 flex flex-wrap items-center gap-1">
          <ChannelStatusBadges ch={ch} media />
        </div>

        <div className="absolute top-2 right-2">
          <TwitchRoleBadge role="bot" size={18} className="drop-shadow-sm opacity-80" />
        </div>

        <div className="absolute inset-x-0 bottom-0 space-y-1 p-2.5">
          {isSuspended && ch.membership_reason && (
            <p className="text-label text-white/70 truncate">停權原因：{ch.membership_reason}</p>
          )}
          <div className="flex items-end gap-2">
            <img
              src={ch.avatar}
              alt={ch.display_name}
              className="size-8 rounded-full border-2 border-white/20 object-cover shrink-0"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sub leading-tight font-semibold text-white truncate">
                {ch.display_name}
              </p>
              <p className="text-label font-mono text-white/60 truncate">{ch.name}</p>
            </div>
            {ch.is_live && <span className="mb-1 size-2 rounded-full bg-status-live shrink-0" />}
          </div>
        </div>
      </button>
      <ScopeDetailDialog
        ch={ch}
        open={open}
        onOpenChange={setOpen}
        onSuspendRequest={
          ch.membership_status === 'active' && ch.owner_user_id && onSuspend
            ? () => setSuspendOpen(true)
            : undefined
        }
        onReinstate={onReinstate}
      />
      {onSuspend && (
        <SuspendMembershipDialog
          ch={ch}
          open={suspendOpen}
          onOpenChange={setSuspendOpen}
          onSuspend={onSuspend}
        />
      )}
    </>
  )
}
