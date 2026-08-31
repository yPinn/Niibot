import type { ChannelDefaults } from '@/api/channels'
import type { CommandConfig } from '@/api/commands'

export const ROLE_LABELS: Record<string, string> = {
  everyone: '所有人',
  subscriber: '訂閱者',
  vip: 'VIP',
  moderator: 'Mod',
  broadcaster: '實況主',
}

export const PUBLIC_ROLE_LABELS: Record<string, string> = {
  everyone: 'For everyone',
  subscriber: 'Subscribers',
  vip: 'VIPs',
}

export const AUDIENCE_LABELS: Record<NonNullable<CommandConfig['audience']>, string> = {
  viewer: '觀眾',
  moderator: 'Mod',
  broadcaster: '實況主',
}

/** Commands whose response text is editable even though they are "builtin". */
export const EDITABLE_COMMANDS = ['hi']

export function formatCooldown(cooldown: number | null, defaults: ChannelDefaults): string {
  const effective = cooldown ?? defaults.default_cooldown
  if (effective <= 0) return '無'
  return `${effective}s`
}
