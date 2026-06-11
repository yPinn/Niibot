import { Icon } from '@/components/primitives'
import { Avatar, AvatarFallback, AvatarImage, Badge, Card } from '@/components/ui'
import { cn } from '@/lib/utils'

import type { MatcherChannelSummary } from './types'

interface ChannelCardProps {
  channel: MatcherChannelSummary
  isSelected: boolean
  onClick: () => void
}

function overlapColor(pct: number): string {
  if (pct >= 30) return 'text-status-online'
  if (pct >= 10) return 'text-status-info'
  return 'text-muted-foreground'
}

function broadcasterBadge(type: string | null) {
  if (type === 'partner')
    return (
      <Badge
        variant="outline"
        className="text-status-loading border-status-loading/40 text-label py-0 shrink-0"
      >
        Partner
      </Badge>
    )
  if (type === 'affiliate')
    return (
      <Badge variant="outline" className="text-primary border-primary/40 text-label py-0 shrink-0">
        Affiliate
      </Badge>
    )
  return null
}

export function ChannelCard({ channel, isSelected, onClick }: ChannelCardProps) {
  const name = channel.display_name ?? channel.channel_id
  const initials = name.slice(0, 2).toUpperCase()
  const recentGame = channel.is_live ? channel.stream_game : (channel.top_games[0] ?? null)

  return (
    <Card
      onClick={onClick}
      className={cn(
        'flex gap-element p-section cursor-pointer select-none transition-colors hover:bg-accent',
        isSelected && 'ring-2 ring-primary'
      )}
    >
      <Avatar className="size-10 shrink-0 mt-0.5">
        <AvatarImage src={channel.profile_image_url ?? undefined} alt={name} />
        <AvatarFallback className="text-label">{initials}</AvatarFallback>
      </Avatar>

      <div className="flex flex-col gap-1 flex-1 min-w-0">
        <div className="flex items-start justify-between gap-element">
          <div className="flex items-center gap-1 flex-wrap flex-1 min-w-0">
            <span className="text-sub font-semibold truncate">{name}</span>
            {broadcasterBadge(channel.broadcaster_type)}
            {channel.is_live && (
              <Badge className="bg-status-live/90 text-white text-label py-0 px-1.5 shrink-0">
                LIVE
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <span
              className={cn(
                'text-card-title font-bold tabular-nums',
                overlapColor(channel.overlap_pct)
              )}
            >
              {channel.overlap_pct.toFixed(1)}%
            </span>
            {channel.login && (
              <a
                href={`https://www.twitch.tv/${channel.login}`}
                target="_blank"
                rel="noopener noreferrer"
                onClick={e => e.stopPropagation()}
                className="text-muted-foreground/50 hover:text-muted-foreground transition-colors"
              >
                <Icon icon="fa-solid fa-arrow-up-right-from-square" className="text-label" />
              </a>
            )}
          </div>
        </div>

        {(recentGame || channel.language || (channel.tags?.length ?? 0) > 0) && (
          <div className="flex items-center gap-1 flex-wrap">
            {recentGame && (
              <span className="text-label text-muted-foreground truncate max-w-30">
                {recentGame}
              </span>
            )}
            {channel.language && (
              <Badge
                variant="outline"
                className="text-label py-0 px-1.5 font-mono uppercase text-muted-foreground shrink-0"
              >
                {channel.language}
              </Badge>
            )}
            {channel.tags.slice(0, 3).map(tag => (
              <Badge
                key={tag}
                variant="outline"
                className="text-label py-0 px-1.5 text-muted-foreground border-border/60 shrink-0"
              >
                {tag}
              </Badge>
            ))}
          </div>
        )}

        <div className="flex items-center gap-1 flex-wrap">
          <Badge variant="secondary" className="text-label py-0">
            {channel.shared_chatters.toLocaleString()} 共同觀眾
          </Badge>
          <Badge variant="secondary" className="text-label py-0">
            {channel.exclusive_to_partner.toLocaleString()} 潛在觀眾
          </Badge>
        </div>
      </div>
    </Card>
  )
}
