import { type ChannelBadges, type ViewerSummary } from '@/api/analytics'
import { type BadgeEntry, type TwitchRole } from '@/components/primitives'

const BITS_TIERS = [
  5000000, 4500000, 4000000, 3500000, 3000000, 2500000, 2000000, 1750000, 1500000, 1250000, 1000000,
  900000, 800000, 700000, 600000, 500000, 400000, 300000, 200000, 100000, 75000, 50000, 25000,
  10000, 5000, 1000, 100, 1,
]
const SUB_GIFTER_TIERS = [
  5000, 4000, 3000, 2000, 1000, 950, 900, 850, 800, 750, 700, 650, 600, 550, 500, 450, 400, 350,
  300, 250, 200, 150, 100, 50, 25, 10, 5, 1,
]

function getBitsTier(n: number): string | null {
  if (n <= 0) return null
  const t = BITS_TIERS.find(v => n >= v)
  return t != null ? String(t) : null
}

function getSubGifterTier(n: number): string | null {
  if (n <= 0) return null
  const t = SUB_GIFTER_TIERS.find(v => n >= v)
  return t != null ? String(t) : null
}

function subGifterBadge(totalGifts: number): { role: TwitchRole; version: string }[] {
  const tier = getSubGifterTier(totalGifts)
  return tier ? [{ role: 'sub_gifter' as TwitchRole, version: tier }] : []
}

function bitsBadge(
  totalBits: number,
  bits?: ChannelBadges['sets']['bits'] | null
): { role: TwitchRole; version: string; src: string | null }[] {
  const tier = getBitsTier(totalBits)
  if (!tier) return []
  const src = bits?.find(v => v.id === tier)?.image_url_1x ?? null
  return [{ role: 'bits' as TwitchRole, version: tier, src }]
}

export type BadgeSource = Pick<
  ViewerSummary,
  'is_mod' | 'is_vip' | 'is_subscribed' | 'total_gifts' | 'total_bits'
>

export function buildViewerBadges(
  v: BadgeSource,
  channelBadges: ChannelBadges | null
): BadgeEntry[] {
  return [
    ...(v.is_mod ? [{ role: 'moderator' as TwitchRole }] : []),
    ...(!v.is_mod && v.is_vip ? [{ role: 'vip' as TwitchRole }] : []),
    ...(v.is_subscribed
      ? [{ role: 'subscriber' as TwitchRole, src: channelBadges?.subscriber_1m ?? undefined }]
      : []),
    ...subGifterBadge(v.total_gifts),
    ...bitsBadge(v.total_bits, channelBadges?.sets?.bits),
  ]
}

export {
  formatCompact,
  formatDate,
  formatDateFull,
  formatDuration,
  formatRelativeDays,
  formatWatchHours,
} from '@/lib/format'
