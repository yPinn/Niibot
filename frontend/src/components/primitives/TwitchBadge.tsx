import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'

// ---------------------------------------------------------------------------
// Shared sizing
// ---------------------------------------------------------------------------

type BadgeSize = 18 | 36 | 72

const SIZE_CONFIG = {
  18: { box: 'size-[66px]', img: 'size-[18px]', label: '18 × 18px', file: '1x.png' },
  36: { box: 'size-[84px]', img: 'size-9', label: '36 × 36px', file: '2x.png' },
  72: { box: 'size-[120px]', img: 'size-[72px]', label: '72 × 72px', file: '4x.png' },
} as const

// ---------------------------------------------------------------------------
// Role types
// global — flat (static files)     : broadcaster, lead_moderator, moderator, artist, vip, partner, bot
// global — versioned (version key) : gift_leader (1/2/3), sub_gifter (1/5/10…), bits (100/1000…)
// channel-specific (src)           : subscriber, founder
// ---------------------------------------------------------------------------

export type TwitchRole =
  | 'broadcaster'
  | 'lead_moderator'
  | 'moderator'
  | 'artist'
  | 'vip'
  | 'gift_leader'
  | 'founder'
  | 'subscriber'
  | 'sub_gifter'
  | 'bits'
  | 'bits_leader'
  | 'partner'
  | 'bot'

const ROLE_LABEL: Record<TwitchRole, string> = {
  broadcaster: '轉播',
  lead_moderator: '主要 Mod',
  moderator: 'Mod',
  artist: '繪師',
  vip: 'VIP',
  gift_leader: '熱門贈禮人',
  founder: '創建者',
  subscriber: '訂閱者',
  sub_gifter: '訂閱贈禮人',
  bits: 'Cheer',
  bits_leader: '熱門Cheerer',
  partner: '已驗證',
  bot: '聊天機器人',
}

function getRoleTooltip(role: TwitchRole, version?: string): string {
  if (!version) return ROLE_LABEL[role]
  const n = parseInt(version, 10)
  switch (role) {
    case 'sub_gifter':
      return n <= 1 ? ROLE_LABEL[role] : `${n.toLocaleString()} 份贈禮訂閱`
    case 'bits':
      return `Cheer ${n.toLocaleString()}`
    case 'gift_leader':
    case 'bits_leader':
      return `${ROLE_LABEL[role]} #${version}`
    default:
      return ROLE_LABEL[role]
  }
}

// ---------------------------------------------------------------------------
// TwitchBadge — channel-specific image badge (subscriber, founder)
// ---------------------------------------------------------------------------

interface TwitchBadgeProps {
  src: string
  alt?: string
  size?: BadgeSize
  className?: string
}

export function TwitchBadge({ src, alt = '', size = 18, className }: TwitchBadgeProps) {
  const img = (
    <img
      src={src}
      alt={alt}
      width={size}
      height={size}
      draggable={false}
      className={cn('object-contain shrink-0 rounded-[3px]', SIZE_CONFIG[size].img, className)}
    />
  )
  if (!alt) return img
  return (
    <Tooltip>
      <TooltipTrigger asChild>{img}</TooltipTrigger>
      <TooltipContent>{alt}</TooltipContent>
    </Tooltip>
  )
}

// ---------------------------------------------------------------------------
// Badge display priority — matches Twitch's official ordering in chat
const ROLE_ORDER: Record<TwitchRole, number> = {
  broadcaster: 0,
  lead_moderator: 1,
  moderator: 2,
  artist: 3,
  vip: 4,
  gift_leader: 5,
  founder: 6,
  subscriber: 7,
  sub_gifter: 8,
  bits_leader: 9,
  bits: 10,
  partner: 11,
  bot: 12,
}

// ---------------------------------------------------------------------------
// TwitchBadgeGroup — sorted badge row with correct Twitch spacing
// ---------------------------------------------------------------------------

export interface BadgeEntry {
  role: TwitchRole
  /** Required for subscriber / founder (channel-specific). */
  src?: string | null
  /** For versioned badges (bits, gift_leader, sub_gifter). Resolves to /twitch-badges/{role}/{version}/{size}.png */
  version?: string
}

interface TwitchBadgeGroupProps {
  badges: BadgeEntry[]
  size?: BadgeSize
  className?: string
}

export function TwitchBadgeGroup({ badges, size = 18, className }: TwitchBadgeGroupProps) {
  const sorted = [...badges].sort((a, b) => ROLE_ORDER[a.role] - ROLE_ORDER[b.role])
  if (!sorted.length) return null
  return (
    <div className={cn('inline-flex items-center gap-0.5 shrink-0', className)}>
      {sorted.map(({ role, src, version }) => (
        <TwitchRoleBadge
          key={`${role}-${version ?? ''}`}
          role={role}
          src={src}
          version={version}
          size={size}
        />
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// TwitchRoleBadge — global role badge from static files
// Pass `src` to override (e.g. channel-specific subscriber badge).
// ---------------------------------------------------------------------------

interface TwitchRoleBadgeProps {
  role: TwitchRole
  /** Override the static file with an explicit URL (channel-specific badges). */
  src?: string | null
  /** Version for tiered badges (bits, gift_leader, sub_gifter). Resolves to /twitch-badges/{role}/{version}/{size}.png */
  version?: string
  size?: BadgeSize
  className?: string
}

export function TwitchRoleBadge({
  role,
  src,
  version,
  size = 18,
  className,
}: TwitchRoleBadgeProps) {
  const resolvedSrc =
    src ??
    (version
      ? `/twitch-badges/${role}/${version}/${SIZE_CONFIG[size].file}`
      : `/twitch-badges/${role}/${SIZE_CONFIG[size].file}`)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <img
          src={resolvedSrc}
          alt={getRoleTooltip(role, version)}
          width={size}
          height={size}
          draggable={false}
          className={cn('object-contain shrink-0 rounded-[3px]', SIZE_CONFIG[size].img, className)}
        />
      </TooltipTrigger>
      <TooltipContent>{getRoleTooltip(role, version)}</TooltipContent>
    </Tooltip>
  )
}

// ---------------------------------------------------------------------------
// TwitchRoleBadgeLabel — inline role chip: badge + text (for list rows)
// ---------------------------------------------------------------------------

interface TwitchRoleBadgeLabelProps {
  role: TwitchRole
  src?: string | null
  className?: string
}

export function TwitchRoleBadgeLabel({ role, src, className }: TwitchRoleBadgeLabelProps) {
  return (
    <span className={cn('inline-flex items-center gap-1.5', className)}>
      <TwitchRoleBadge role={role} src={src} size={18} />
      <span className="text-sub text-foreground">{ROLE_LABEL[role]}</span>
    </span>
  )
}

// ---------------------------------------------------------------------------
// Shared size-box used by both preview components
// ---------------------------------------------------------------------------

function SizeBox({ children, size }: { children: React.ReactNode; size: BadgeSize }) {
  const { box, label } = SIZE_CONFIG[size]
  return (
    <div className="flex flex-col items-center gap-2">
      <div
        className={cn(
          'flex shrink-0 items-center justify-center rounded-md',
          'border border-dashed border-border/60 bg-muted/20',
          box
        )}
      >
        {children}
      </div>
      <span className="text-label text-muted-foreground tabular-nums">{label}</span>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TwitchBadgePreview — subscriber / founder badge preview (3 sizes)
// ---------------------------------------------------------------------------

interface TwitchBadgePreviewProps {
  image_url_1x: string | null
  image_url_2x: string | null
  image_url_4x: string | null
  className?: string
}

export function TwitchBadgePreview({
  image_url_1x,
  image_url_2x,
  image_url_4x,
  className,
}: TwitchBadgePreviewProps) {
  const fallback = image_url_1x ?? image_url_2x ?? image_url_4x
  if (!fallback) return null

  return (
    <div className={cn('flex items-end gap-3', className)}>
      <SizeBox size={18}>
        <TwitchBadge src={image_url_1x ?? fallback} size={18} />
      </SizeBox>
      <SizeBox size={36}>
        <TwitchBadge src={image_url_2x ?? fallback} size={36} />
      </SizeBox>
      <SizeBox size={72}>
        <TwitchBadge src={image_url_4x ?? fallback} size={72} />
      </SizeBox>
    </div>
  )
}

// ---------------------------------------------------------------------------
// TwitchRoleBadgePreview — role badge preview (3 sizes, from static files)
// ---------------------------------------------------------------------------

interface TwitchRoleBadgePreviewProps {
  role: TwitchRole
  /** Override static files with explicit URLs (channel-specific badges). */
  image_url_1x?: string | null
  image_url_2x?: string | null
  image_url_4x?: string | null
  className?: string
}

export function TwitchRoleBadgePreview({
  role,
  image_url_1x,
  image_url_2x,
  image_url_4x,
  className,
}: TwitchRoleBadgePreviewProps) {
  return (
    <div className={cn('flex items-end gap-3', className)}>
      <SizeBox size={18}>
        <TwitchRoleBadge role={role} src={image_url_1x} size={18} />
      </SizeBox>
      <SizeBox size={36}>
        <TwitchRoleBadge role={role} src={image_url_2x} size={36} />
      </SizeBox>
      <SizeBox size={72}>
        <TwitchRoleBadge role={role} src={image_url_4x} size={72} />
      </SizeBox>
    </div>
  )
}
