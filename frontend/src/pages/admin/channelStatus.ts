import type { AdminChannel } from '@/api/admin'

export type ChannelCategory = 'issues' | 'pending' | 'healthy' | 'paused' | 'suspended'

export type ChannelIssueKind = 'scope' | 'token' | 'no_mod' | 'provider'

export interface ChannelStatusPresentation {
  label: string
  icon: string
  className: string
}

export interface ChannelIssue extends ChannelStatusPresentation {
  kind: ChannelIssueKind
}

/** Why an admitted, enabled channel isn't monitored cleanly — or null when it
 * is. The single source for both the admin grouping and the card's badge, so
 * the two can never disagree about a channel. */
export function getChannelIssue(ch: AdminChannel): ChannelIssue | null {
  if (ch.missing_scopes.length > 0 || ch.mod_status === 'scope_error') {
    const count = ch.missing_scopes.length
    return {
      kind: 'scope',
      label: count > 0 ? `缺少 ${count} 項權限` : '授權不足',
      icon: 'fa-solid fa-lock',
      className: 'border-status-info/20 bg-status-info/10 text-status-info',
    }
  }
  if (ch.mod_status === 'token_error') {
    return {
      kind: 'token',
      label: 'Token 過期',
      icon: 'fa-solid fa-rotate-exclamation',
      className: 'border-status-warning/20 bg-status-warning/10 text-status-warning',
    }
  }
  if (ch.mod_status === 'no_mod') {
    return {
      kind: 'no_mod',
      label: 'Bot 非管理員',
      icon: 'fa-solid fa-shield-xmark',
      className: 'border-status-offline/20 bg-status-offline/10 text-status-offline',
    }
  }
  if (ch.mod_status !== 'mod') {
    // provider_unavailable, or 'error' when the backend's check itself threw.
    return {
      kind: 'provider',
      label: '無法確認狀態',
      icon: 'fa-solid fa-triangle-exclamation',
      className: 'border-border bg-muted text-muted-foreground',
    }
  }
  return null
}

export function getChannelCategory(ch: AdminChannel): ChannelCategory {
  if (ch.membership_status === 'pending') return 'pending'
  if (ch.membership_status === 'suspended') return 'suspended'
  if (!ch.is_enabled) return 'paused'
  return getChannelIssue(ch) ? 'issues' : 'healthy'
}
