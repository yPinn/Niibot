import { useState } from 'react'

import type { AdminChannel, ModStatus } from '@/api/admin'
import { Icon, Spinner, TwitchRoleBadge, TwitchRoleBadgeLabel } from '@/components/primitives'
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
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
  suspended: '授權已暫停，bot 暫停監控此頻道',
}

// ── Scope detail dialog ───────────────────────────────────────────────────────

function ScopeDetailDialog({
  ch,
  open,
  onOpenChange,
  onReinstate,
}: {
  ch: AdminChannel
  open: boolean
  onOpenChange: (v: boolean) => void
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
          <div className="flex flex-col gap-element mt-1">
            <TwitchRoleBadgeLabel role="bot" />
            {ch.membership_status === 'pending' || ch.membership_status === 'suspended' ? (
              <span className="text-sub text-muted-foreground">
                {MEMBERSHIP_STATUS_LABEL[ch.membership_status]}
              </span>
            ) : (
              <ModStatusBadge
                status={ch.is_bot ? 'broadcaster' : ch.mod_status}
                missingCount={ch.missing_scopes.length}
                bare
              />
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

function PendingStatusIcon() {
  return (
    <span className="inline-flex items-center justify-center size-4.5 rounded border-status-info/20 bg-status-info/10 text-status-info">
      <Icon icon="fa-solid fa-hourglass-half" size="badge" />
    </span>
  )
}

function SuspendedStatusIcon() {
  return (
    <span className="inline-flex items-center justify-center size-4.5 rounded border-destructive/20 bg-destructive/10 text-destructive">
      <Icon icon="fa-solid fa-ban" size="badge" />
    </span>
  )
}

export function ChannelCard({
  ch,
  onReinstate,
}: {
  ch: AdminChannel
  onReinstate?: (ch: AdminChannel) => void | Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const status: ModStatus = ch.is_bot ? 'broadcaster' : ch.mod_status
  const isPending = ch.membership_status === 'pending'
  const isSuspended = ch.membership_status === 'suspended'
  const isPaused = !ch.is_enabled
  const isDimmed = isPaused || isPending || isSuspended

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={`relative w-full aspect-video rounded-lg border border-border overflow-hidden hover:ring-2 hover:ring-primary transition-all select-none${isDimmed ? ' opacity-50 grayscale' : ''}`}
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
          {isSuspended ? (
            <SuspendedStatusIcon />
          ) : isPending ? (
            <PendingStatusIcon />
          ) : isPaused ? (
            <PauseStatusIcon />
          ) : (
            <ModStatusIcon status={status} />
          )}
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
      <ScopeDetailDialog ch={ch} open={open} onOpenChange={setOpen} onReinstate={onReinstate} />
    </>
  )
}
