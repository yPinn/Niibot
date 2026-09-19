import { Avatar, AvatarFallback, AvatarImage, Badge } from '@/components/ui'
import { cn } from '@/lib/utils'

import { broadcasterBadge } from './badges'
import { type CompatibilityTier, type MatcherChannelSummary, TIER_COLOR } from './types'

interface ChannelDetailHeaderProps {
  channel: MatcherChannelSummary
  tier: CompatibilityTier
}

/** Self-contained channel identity block for the detail panel — kept isolated
 * from the sections below it (CollabLog, metrics grid, common ground) so its
 * layout stays fixed no matter what renders alongside it. */
export function ChannelDetailHeader({ channel, tier }: ChannelDetailHeaderProps) {
  const name = channel.display_name ?? channel.channel_id
  const initials = name.slice(0, 2).toUpperCase()

  return (
    <div className="flex items-start gap-3 shrink-0">
      <Avatar className="size-12 shrink-0">
        <AvatarImage src={channel.profile_image_url ?? undefined} alt={name} />
        <AvatarFallback className="text-sub">{initials}</AvatarFallback>
      </Avatar>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-card-title font-semibold">{name}</span>
          <Badge variant="outline" className={cn('text-label py-0 shrink-0', TIER_COLOR[tier])}>
            契合度 {tier}
          </Badge>
          {broadcasterBadge(channel.broadcaster_type)}
          {channel.language && (
            <Badge
              variant="outline"
              className="text-label py-0 font-mono uppercase text-muted-foreground shrink-0"
            >
              {channel.language}
            </Badge>
          )}
          {channel.is_live && (
            <div className="flex items-center gap-1.5">
              <span className="size-2 rounded-full bg-status-live shrink-0" />
              <span className="text-label text-muted-foreground">
                {channel.viewer_count.toLocaleString()} 人觀看
              </span>
            </div>
          )}
        </div>
        {channel.is_live && channel.stream_title && (
          <p className="text-label text-muted-foreground truncate mt-0.5">
            {channel.stream_game && <span className="mr-1">[{channel.stream_game}]</span>}
            {channel.stream_title}
          </p>
        )}
        {channel.description && (
          <p className="text-label text-muted-foreground line-clamp-2 mt-1">
            {channel.description}
          </p>
        )}
      </div>
    </div>
  )
}
