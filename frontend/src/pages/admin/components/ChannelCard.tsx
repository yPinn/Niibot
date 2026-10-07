import { useState } from 'react'

import type { AdminChannel } from '@/api/admin'
import { Icon, Spinner } from '@/components/primitives'
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

import { type ChannelStatusPresentation, getChannelIssue } from '../channelStatus'

import { ScopeSection } from './ScopeSection'

// ── Membership status config ────────────────────────────────────────────────

const SUSPENSION_REASON_PRESETS = [
  '違反使用規範',
  '濫用或惡意操作',
  '帳號安全風險',
  '管理員人工審查',
] as const

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

/** One status per channel: membership when it isn't active (pending and
 * suspended already imply the bot isn't monitoring), otherwise monitoring. */
function getChannelStatus(ch: AdminChannel): ChannelStatusPresentation {
  if (ch.membership_status !== 'active') return getMembershipStatus(ch)
  if (!ch.is_enabled) {
    return {
      label: '監控暫停',
      icon: 'fa-solid fa-circle-pause',
      className: 'border-border bg-muted text-muted-foreground',
    }
  }
  return (
    getChannelIssue(ch) ?? {
      label: '監控正常',
      icon: 'fa-solid fa-shield-check',
      className: 'border-status-online/20 bg-status-online/10 text-status-online',
    }
  )
}

function StatusBadge({
  item,
  media = false,
}: {
  item: ChannelStatusPresentation
  media?: boolean
}) {
  return (
    <Badge
      className={`gap-1 text-label ${media ? 'shadow-sm backdrop-blur-sm' : ''} ${item.className}`}
    >
      <Icon icon={item.icon} size="badge" />
      {item.label}
    </Badge>
  )
}

/** Resolves true when the action committed, so the dialog knows to close. */
export type ChannelAction = (ch: AdminChannel) => Promise<boolean>

// ── Scope detail dialog ───────────────────────────────────────────────────────

function ScopeDetailDialog({
  ch,
  open,
  onOpenChange,
  onSuspendRequest,
  onReinstate,
  onApprove,
  onReject,
  onRecheck,
}: {
  ch: AdminChannel
  open: boolean
  onOpenChange: (v: boolean) => void
  onSuspendRequest?: () => void
  onReinstate?: ChannelAction
  onApprove?: ChannelAction
  onReject?: ChannelAction
  onRecheck?: () => Promise<void>
}) {
  const [busy, setBusy] = useState<'reinstate' | 'approve' | 'reject' | 'recheck' | null>(null)
  const [confirmingReject, setConfirmingReject] = useState(false)
  const issue = ch.membership_status === 'active' && ch.is_enabled ? getChannelIssue(ch) : null

  const handleOpenChange = (next: boolean) => {
    if (!next) setConfirmingReject(false)
    onOpenChange(next)
  }

  const run = async (kind: 'reinstate' | 'approve' | 'reject', action?: ChannelAction) => {
    if (!action) return
    setBusy(kind)
    try {
      if (await action(ch)) handleOpenChange(false)
    } finally {
      setBusy(null)
    }
  }

  const recheck = async () => {
    if (!onRecheck) return
    setBusy('recheck')
    try {
      await onRecheck()
    } finally {
      setBusy(null)
    }
  }

  // Credential and mod issues already prompt the broadcaster in-app (reauth
  // toast, ModSetupDialog); an unconfirmed status is the only one the admin
  // can act on from here.
  const canRecheck = issue?.kind === 'provider' && onRecheck
  const hasAction =
    canRecheck ||
    (ch.membership_status === 'active' && onSuspendRequest) ||
    (ch.membership_status === 'suspended' && onReinstate) ||
    (ch.membership_status === 'pending' && (onApprove || onReject))

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <div className="flex items-center gap-element">
            <img
              src={ch.avatar}
              alt={ch.display_name}
              className="size-9 rounded-full object-cover shrink-0"
            />
            <div className="min-w-0">
              <DialogTitle>
                <a
                  href={`https://www.twitch.tv/${ch.name}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 hover:underline"
                >
                  {ch.display_name}
                  <Icon
                    icon="fa-solid fa-arrow-up-right-from-square"
                    size="xs"
                    wrapperClassName="text-muted-foreground"
                  />
                </a>
              </DialogTitle>
              <DialogDescription className="font-mono">{ch.name}</DialogDescription>
            </div>
          </div>
          <div className="mt-1">
            <StatusBadge item={getChannelStatus(ch)} />
          </div>
        </DialogHeader>
        {ch.missing_scopes.length > 0 && (
          <ScopeSection title="缺少權限" granted={[]} missing={ch.missing_scopes} />
        )}
        {ch.membership_status === 'suspended' && ch.membership_reason && (
          <div className="space-y-element rounded-md bg-muted p-3">
            <p className="text-label font-medium text-muted-foreground">停權原因</p>
            <p className="text-sub whitespace-pre-wrap break-words">{ch.membership_reason}</p>
          </div>
        )}
        {hasAction && (
          <DialogFooter>
            {ch.membership_status === 'active' && onSuspendRequest && (
              // Destructive and rarely right, so it stays quiet next to the fix.
              <Button
                variant="ghost"
                size="sm"
                className="text-destructive hover:bg-destructive/10 hover:text-destructive"
                onClick={() => {
                  handleOpenChange(false)
                  onSuspendRequest()
                }}
              >
                <Icon icon="fa-solid fa-ban" size="xs" />
                停權使用者
              </Button>
            )}
            {canRecheck && (
              <Button onClick={() => void recheck()} disabled={busy !== null}>
                {busy === 'recheck' ? <Spinner /> : <Icon icon="fa-solid fa-rotate" size="xs" />}
                重新檢查
              </Button>
            )}
            {ch.membership_status === 'suspended' && onReinstate && (
              <Button onClick={() => void run('reinstate', onReinstate)} disabled={busy !== null}>
                {busy === 'reinstate' ? (
                  <Spinner />
                ) : (
                  <Icon icon="fa-solid fa-rotate-left" size="xs" />
                )}
                恢復授權
              </Button>
            )}
            {ch.membership_status === 'pending' && onReject && (
              <Button
                variant="outline"
                className="text-destructive border-destructive/30 hover:bg-destructive/10 hover:text-destructive"
                onClick={() =>
                  confirmingReject ? void run('reject', onReject) : setConfirmingReject(true)
                }
                disabled={busy !== null}
              >
                {busy === 'reject' && <Spinner />}
                {confirmingReject ? '確認拒絕' : '拒絕'}
              </Button>
            )}
            {ch.membership_status === 'pending' && onApprove && (
              <Button onClick={() => void run('approve', onApprove)} disabled={busy !== null}>
                {busy === 'approve' ? <Spinner /> : <Icon icon="fa-solid fa-check" size="xs" />}
                核准
              </Button>
            )}
          </DialogFooter>
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
          <DialogDescription>Bot 會停止監控，資料保留，可隨時恢復。</DialogDescription>
        </DialogHeader>

        <div className="space-y-section">
          <Select
            value={preset}
            onValueChange={value => {
              setPreset(value)
              setReason(value)
            }}
            disabled={submitting}
          >
            <SelectTrigger className="w-full" aria-label="常見原因">
              <SelectValue placeholder="常見原因" />
            </SelectTrigger>
            <SelectContent>
              {SUSPENSION_REASON_PRESETS.map(item => (
                <SelectItem key={item} value={item}>
                  {item}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

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
              placeholder="或輸入原因"
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
  onApprove,
  onReject,
  onRecheck,
}: {
  ch: AdminChannel
  onSuspend?: (ch: AdminChannel, reason: string) => Promise<boolean>
  onReinstate?: ChannelAction
  onApprove?: ChannelAction
  onReject?: ChannelAction
  onRecheck?: () => Promise<void>
}) {
  const [open, setOpen] = useState(false)
  const [suspendOpen, setSuspendOpen] = useState(false)
  const isDimmed = !ch.is_enabled || ch.membership_status !== 'active'
  const status = getChannelStatus(ch)
  // The grid already groups cards by state, so the card only surfaces what
  // the group can't say: the concrete reason an "issues" channel needs work.
  const issue = ch.membership_status === 'active' && ch.is_enabled ? getChannelIssue(ch) : null
  const ariaLabel = [ch.display_name, ch.is_live && '直播中', status.label]
    .filter(Boolean)
    .join('，')

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={ariaLabel}
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

        {issue && (
          <div className="absolute top-2 left-2 right-2">
            <StatusBadge item={issue} media />
          </div>
        )}

        <div className="absolute inset-x-0 bottom-0 space-y-1 p-2.5">
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
            {ch.is_live && (
              <span aria-hidden className="mb-1 size-2 rounded-full bg-status-live shrink-0" />
            )}
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
        onApprove={onApprove}
        onReject={onReject}
        onRecheck={onRecheck}
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
