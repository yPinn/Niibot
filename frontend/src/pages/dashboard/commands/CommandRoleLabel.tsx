import { Icon } from '@/components/primitives'
import type { TwitchRole } from '@/components/primitives/TwitchBadge'
import { TwitchRoleBadge } from '@/components/primitives/TwitchBadge'
import { cn } from '@/lib/utils'

import { ROLE_LABELS } from './constants'

const TWITCH_ROLE: Partial<Record<string, TwitchRole>> = {
  subscriber: 'subscriber',
  vip: 'vip',
  moderator: 'moderator',
  broadcaster: 'broadcaster',
}

interface CommandRoleLabelProps {
  role: string
  compact?: boolean
  className?: string
}

export function CommandRoleLabel({ role, compact = false, className }: CommandRoleLabelProps) {
  const label = ROLE_LABELS[role] ?? role
  const twitchRole = TWITCH_ROLE[role]

  return (
    <span className={cn('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap', className)}>
      {twitchRole ? (
        <TwitchRoleBadge role={twitchRole} label={label} size={18} decorative />
      ) : (
        <Icon icon="fa-solid fa-users" wrapperClassName="size-3.5 text-muted-foreground" />
      )}
      <span className={compact ? 'text-label' : 'text-sub'}>{label}</span>
    </span>
  )
}
