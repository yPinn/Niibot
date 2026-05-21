import { Avatar, AvatarFallback, AvatarImage, Badge, Card, Icon } from '@/components/ui'
import { cn } from '@/lib/utils'

import type { MatcherChannelSummary } from './types'

interface ChannelCardProps {
  channel: MatcherChannelSummary
  isSelected: boolean
  onClick: () => void
}

function overlapColor(pct: number): string {
  if (pct >= 30) return 'text-green-500'
  if (pct >= 10) return 'text-blue-500'
  return 'text-muted-foreground'
}

function broadcasterBadge(type: string | null) {
  if (type === 'partner')
    return (
      <Badge
        variant="outline"
        className="text-yellow-500 border-yellow-500/40 text-[10px] py-0 shrink-0"
      >
        Partner
      </Badge>
    )
  if (type === 'affiliate')
    return (
      <Badge
        variant="outline"
        className="text-purple-500 border-purple-500/40 text-[10px] py-0 shrink-0"
      >
        Affiliate
      </Badge>
    )
  return null
}

function formatPeakHours(hours: number[]): string | null {
  if (!hours.length) return null
  const min = Math.min(...hours)
  const max = Math.max(...hours)
  return min === max ? `${min}:00` : `${min}:00–${max}:59`
}

export function ChannelCard({ channel, isSelected, onClick }: ChannelCardProps) {
  const name = channel.display_name ?? channel.channel_id
  const initials = name.slice(0, 2).toUpperCase()
  const peakHours = formatPeakHours(channel.peak_hours)
  const displayGames = channel.top_games.length > 0 ? channel.top_games : null

  return (
    <Card
      onClick={onClick}
      className={cn(
        'flex flex-col gap-2 p-3 cursor-pointer transition-colors hover:bg-accent',
        isSelected && 'ring-2 ring-primary'
      )}
    >
      {/* Row 1: avatar + name + badges */}
      <div className="flex items-start gap-2.5">
        <Avatar className="size-10 shrink-0">
          <AvatarImage src={channel.profile_image_url ?? undefined} alt={name} />
          <AvatarFallback className="text-xs">{initials}</AvatarFallback>
        </Avatar>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-content font-medium truncate">{name}</span>
            {broadcasterBadge(channel.broadcaster_type)}
            {channel.is_live && (
              <div className="flex items-center gap-1">
                <span className="size-1.5 rounded-full bg-red-500 shrink-0" />
                <span className="text-[10px] text-muted-foreground">
                  {channel.viewer_count.toLocaleString()}
                </span>
              </div>
            )}
          </div>

          {/* Games */}
          {displayGames && (
            <div className="flex items-center gap-1 mt-1 flex-wrap">
              {displayGames.slice(0, 3).map(game => (
                <Badge key={game} variant="secondary" className="text-[10px] py-0 px-1.5">
                  {game}
                </Badge>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Row 2: streaming time + session stats */}
      {(peakHours || channel.session_count > 0) && (
        <div className="flex items-center gap-3 text-[10px] text-muted-foreground flex-wrap">
          {peakHours && (
            <span className="flex items-center gap-1">
              <Icon icon="fa-regular fa-clock" className="text-[10px]" />
              {peakHours}
            </span>
          )}
          {channel.session_count > 0 && (
            <span className="flex items-center gap-1">
              <Icon icon="fa-solid fa-video" className="text-[10px]" />
              {channel.session_count} 場次
              {channel.avg_stream_hours > 0 && ` · 均 ${channel.avg_stream_hours}h`}
            </span>
          )}
        </div>
      )}

      {/* Row 3: overlap stats */}
      <div className="flex items-center gap-1.5 flex-wrap">
        <Badge variant="secondary" className="text-[10px] py-0">
          {channel.shared_chatters.toLocaleString()} 共同
        </Badge>
        <Badge variant="secondary" className="text-[10px] py-0">
          {channel.exclusive_to_partner.toLocaleString()} 潛在
        </Badge>
        <Badge
          variant="outline"
          className={cn('text-[10px] py-0', overlapColor(channel.overlap_pct))}
        >
          {channel.overlap_pct.toFixed(1)}%
        </Badge>
      </div>
    </Card>
  )
}
