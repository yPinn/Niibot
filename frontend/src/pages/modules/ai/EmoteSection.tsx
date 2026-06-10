import type { EmoteItem } from '@/api/aiSettings'
import type { ChannelBadges } from '@/api/analytics'
import { TwitchBadge } from '@/components/primitives'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'

function getBadgeOverlay(
  emote: EmoteItem,
  channelBadges: ChannelBadges | null
): { src: string; label: string } | null {
  if (emote.emote_type === 'subscriptions') {
    return {
      src: channelBadges?.subscriber_1m ?? '/twitch-badges/subscriber/1x.png',
      label: '訂閱限定',
    }
  }
  return null
}

export function EmoteChip({
  emote,
  prefix,
  available,
  channelBadges,
}: {
  emote: EmoteItem
  prefix: string
  available: boolean
  channelBadges: ChannelBadges | null
}) {
  const badgeOverlay = getBadgeOverlay(emote, channelBadges)
  const displayName =
    prefix && emote.name.startsWith(prefix) ? emote.name.slice(prefix.length) : emote.name
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={`relative flex select-none flex-col items-center gap-1 rounded-md border border-transparent p-1.5 transition-opacity ${
            available ? '' : 'opacity-40'
          }`}
        >
          {badgeOverlay && (
            <span className="absolute top-1 right-1 rounded-sm bg-black/60 p-0.5">
              <TwitchBadge src={badgeOverlay.src} alt="" size={18} />
            </span>
          )}

          <img
            src={emote.url}
            alt={displayName}
            className="h-14 w-14 object-contain"
            loading="lazy"
          />
          <span className="text-label text-muted-foreground max-w-14 truncate">{displayName}</span>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>{emote.name}</p>
        {!available && <p className="mt-0.5 text-muted-foreground">Bot 無法使用</p>}
      </TooltipContent>
    </Tooltip>
  )
}

export function EmoteSection({
  label,
  emotes,
  prefix,
  channelBadges,
}: {
  label: string
  emotes: EmoteItem[]
  prefix: string
  channelBadges: ChannelBadges | null
}) {
  if (emotes.length === 0) return null
  return (
    <div className="flex flex-col gap-element">
      <span className="text-sub text-muted-foreground">{label}</span>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(5rem,1fr))] gap-1">
        {emotes.map(emote => (
          <EmoteChip
            key={emote.id}
            emote={emote}
            prefix={prefix}
            available={emote.available}
            channelBadges={channelBadges}
          />
        ))}
      </div>
    </div>
  )
}
