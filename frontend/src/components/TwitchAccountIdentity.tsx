import type { ReactNode } from 'react'

import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui'
import { cn } from '@/lib/utils'

interface TwitchAccountIdentityProps {
  avatar?: string | null
  displayName: string
  login: string
  label?: ReactNode
  badges?: ReactNode
  meta?: ReactNode
  size?: 'default' | 'large'
  className?: string
}

export function TwitchAccountIdentity({
  avatar,
  displayName,
  login,
  label,
  badges,
  meta,
  size = 'default',
  className,
}: TwitchAccountIdentityProps) {
  const name = displayName || login
  const initials = name.trim().slice(0, 2).toUpperCase() || 'T'

  return (
    <div className={cn('flex min-w-0 items-center gap-section', className)}>
      <Avatar
        className={size === 'large' ? 'size-12' : 'size-10'}
        role="img"
        aria-label={`${name} 的 Twitch 大頭貼`}
      >
        <AvatarImage src={avatar || undefined} alt="" />
        <AvatarFallback className="text-label font-semibold">{initials}</AvatarFallback>
      </Avatar>

      <div className="min-w-0 flex-1">
        {label ? <div className="text-label text-muted-foreground">{label}</div> : null}
        <div className="flex min-w-0 flex-wrap items-center gap-element">
          <span
            className={cn(
              'truncate font-semibold',
              size === 'large' ? 'text-card-title' : 'text-content'
            )}
          >
            {name}
          </span>
          {badges}
        </div>
        <p className="truncate font-mono text-label text-muted-foreground">@{login}</p>
        {meta ? <div className="text-label text-muted-foreground">{meta}</div> : null}
      </div>
    </div>
  )
}
