import { type ChannelBadges, type ViewerSummary } from '@/api/analytics'
import { type BadgeEntry, type TwitchRole } from '@/components/ui'

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

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-TW', { month: 'short', day: 'numeric' })
}

export function formatDateFull(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('zh-TW', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  })
}

export function formatDuration(seconds: number): string {
  if (!seconds || !Number.isFinite(seconds) || seconds <= 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return m > 0 ? `${h}h ${m}m` : `${h}h`
  return `${m}m`
}

export function formatCompact(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return n.toLocaleString()
}

export function formatWatchHours(sec: number): string {
  if (sec < 60) return '<1分'
  if (sec < 3600) return `${Math.floor(sec / 60)}分`
  return `${(sec / 3600).toFixed(1)}h`
}

export function formatRelativeDays(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / 86_400_000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  if (days < 30) return `${Math.floor(days / 7)} 週前`
  return `${Math.floor(days / 30)} 個月前`
}
