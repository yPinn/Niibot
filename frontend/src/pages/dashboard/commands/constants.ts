import type { ChannelDefaults } from '@/api/channels'

export const ROLE_LABELS: Record<string, string> = {
  everyone: '所有人',
  subscriber: '訂閱者',
  vip: 'VIP',
  moderator: '管理員',
  broadcaster: '頻道主',
}

/** Commands whose response text is editable even though they are "builtin". */
export const EDITABLE_COMMANDS = ['hi']

export function formatCooldown(cooldown: number | null, defaults: ChannelDefaults): string {
  const effective = cooldown ?? defaults.default_cooldown
  if (effective <= 0) return '無'
  return `${effective}s`
}
