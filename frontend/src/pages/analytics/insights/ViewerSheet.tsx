import React, { useEffect, useReducer } from 'react'

import { type ChannelBadges, getViewerProfile, type ViewerProfile } from '@/api/analytics'
import { Icon, type TwitchRole, TwitchRoleBadge } from '@/components/primitives'
import {
  Badge,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetSection,
  SheetTitle,
  Skeleton,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui'
import { cn } from '@/lib/utils'

import { formatCompact, formatDate, formatDateFull, formatDuration } from './utils'
import { HEATMAP_COLS, ViewerHeatmap } from './ViewerHeatmap'

const EVENT_META: Record<string, { icon: string; label: string; color: string }> = {
  follow: { icon: 'fa-solid fa-heart', label: '追隨', color: 'text-status-follow' },
  subscribe: { icon: 'fa-solid fa-star', label: '訂閱', color: 'text-status-special' },
  cheer: { icon: 'fa-solid fa-diamond-half-stroke', label: 'Cheer', color: 'text-primary' },
  raid: { icon: 'fa-solid fa-parachute-box', label: '揪團', color: 'text-status-info' },
}

const SUB_TIER_LABEL: Record<string, string> = {
  '1': '層級 1',
  T1: '層級 1',
  '2': '層級 2',
  T2: '層級 2',
  '3': '層級 3',
  T3: '層級 3',
}

export interface ViewerSheetProps {
  userId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  days: number
  channelBadges: ChannelBadges | null
}

function ProfileAvatar({
  src,
  name,
  size,
}: {
  src?: string | null
  name: string
  size: 'lg' | 'sm'
}) {
  const cls = size === 'lg' ? 'h-16 w-16 ring-2 ring-background' : 'h-11 w-11 shrink-0'
  return src ? (
    <img src={src} alt={name} className={`${cls} rounded-full object-cover`} />
  ) : (
    <div
      className={`${cls} rounded-full bg-muted flex items-center justify-center text-sub font-bold text-muted-foreground select-none`}
    >
      {name.charAt(0).toUpperCase()}
    </div>
  )
}

function UsernameLink({ username }: { username: string | undefined }) {
  if (!username) return <span>觀眾資料</span>
  return (
    <a
      href={`https://twitch.tv/${username}`}
      target="_blank"
      rel="noopener noreferrer"
      className="select-text hover:text-foreground hover:underline transition-colors"
    >
      @{username}
    </a>
  )
}

function PartnerBadge() {
  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="shrink-0 inline-flex">
            <Icon icon="fa-solid fa-circle-check" size="sm" wrapperClassName="text-primary" />
          </span>
        </TooltipTrigger>
        <TooltipContent>合作夥伴</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

function StatusRow({
  icon,
  role,
  badgeSrc,
  iconClass,
  children,
}: {
  icon?: string
  role?: TwitchRole
  badgeSrc?: string | null
  iconClass?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-3">
      {role ? (
        <TwitchRoleBadge role={role} src={badgeSrc ?? null} size={18} />
      ) : (
        <Icon icon={icon!} size="badge" wrapperClassName={cn('shrink-0', iconClass)} />
      )}
      <span className="text-sub text-foreground">{children}</span>
    </div>
  )
}

function StatTile({
  icon,
  value,
  label,
  tooltip,
  badge,
}: {
  icon: string
  value: string
  label: string
  tooltip?: string
  badge?: string
}) {
  const inner = (
    <div className="rounded-md border bg-card p-3 flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <p className="text-label text-muted-foreground">{label}</p>
        {badge != null && (
          <Badge
            variant="outline"
            className="rounded-sm text-muted-foreground tabular-nums font-normal"
          >
            {badge}
          </Badge>
        )}
      </div>
      <div className="flex items-center justify-between">
        <p className="text-card-title font-bold tabular-nums leading-none">{value}</p>
        <Icon icon={icon} size="sm" wrapperClassName="text-primary/70" />
      </div>
    </div>
  )

  if (!tooltip) return inner

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>{inner}</TooltipTrigger>
        <TooltipContent>{tooltip}</TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}

type ViewerSheetState = { profile: ViewerProfile | null; loading: boolean }
type ViewerSheetAction =
  { type: 'reset' } | { type: 'success'; payload: ViewerProfile } | { type: 'error' }

function viewerSheetReducer(_: ViewerSheetState, action: ViewerSheetAction): ViewerSheetState {
  if (action.type === 'reset') return { profile: null, loading: true }
  if (action.type === 'success') return { profile: action.payload, loading: false }
  return { profile: null, loading: false }
}

export function ViewerSheet({ userId, open, onOpenChange, days, channelBadges }: ViewerSheetProps) {
  const [{ profile, loading }, dispatch] = useReducer(viewerSheetReducer, {
    profile: null,
    loading: true,
  })

  useEffect(() => {
    if (!userId || !open) return

    let cancelled = false
    dispatch({ type: 'reset' })
    getViewerProfile(userId, days)
      .then(data => {
        if (!cancelled) dispatch({ type: 'success', payload: data })
      })
      .catch(() => {
        if (!cancelled) dispatch({ type: 'error' })
      })

    return () => {
      cancelled = true
    }
  }, [userId, open, days])

  const name = profile?.display_name || profile?.username || userId || '—'
  const username = profile?.username
  const twitch = profile?.twitch
  const isPartner = profile?.broadcaster_type === 'partner'
  const totalGifts = profile?.total_gifts ?? 0

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-sm p-0 overflow-y-auto flex flex-col select-none">
        {/* Header */}
        {loading ? (
          <SheetHeader className="pr-10 shrink-0">
            <SheetTitle className="sr-only">載入觀眾資料</SheetTitle>
            <SheetDescription className="sr-only">正在載入</SheetDescription>
            <div className="flex items-center gap-3">
              <Skeleton className="h-11 w-11 rounded-full shrink-0" />
              <div className="space-y-1.5 flex-1 min-w-0">
                <Skeleton className="h-5 w-36" />
                <Skeleton className="h-4 w-24" />
              </div>
            </div>
          </SheetHeader>
        ) : profile?.offline_image_url ? (
          <div className="shrink-0">
            <SheetTitle className="sr-only">{name}</SheetTitle>
            <SheetDescription className="sr-only">
              {username ? `@${username}` : '觀眾資料'}
            </SheetDescription>
            <div className="relative">
              <img
                src={profile.offline_image_url}
                alt=""
                className="w-full h-24 object-cover object-center"
              />
              <div className="absolute inset-x-0 bottom-0 h-3/4 bg-linear-to-t from-background via-background/50 to-transparent" />
            </div>
            <div className="relative z-raised flex items-end gap-3 px-page pb-3 pr-12 -mt-8">
              <div className="shrink-0 relative z-raised">
                <ProfileAvatar src={profile.profile_image_url} name={name} size="lg" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-content font-semibold leading-snug truncate select-text">
                    {name}
                  </span>
                  {isPartner && <PartnerBadge />}
                </div>
                <p className="text-label text-muted-foreground mt-0.5">
                  <UsernameLink username={username} />
                </p>
              </div>
            </div>
          </div>
        ) : (
          <SheetHeader className="pr-10 shrink-0">
            <div className="flex items-center gap-3">
              <ProfileAvatar src={profile?.profile_image_url} name={name} size="sm" />
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <SheetTitle className="text-content leading-snug select-text">{name}</SheetTitle>
                  {isPartner && <PartnerBadge />}
                </div>
                <SheetDescription className="text-label mt-0.5">
                  <UsernameLink username={username} />
                </SheetDescription>
              </div>
            </div>
          </SheetHeader>
        )}

        {loading ? (
          <>
            <SheetSection className="space-y-3">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="h-4 w-40" />
            </SheetSection>
            <SheetSection>
              <div className="flex flex-col gap-2">
                <div className="flex justify-between">
                  <Skeleton className="h-3.5 w-16" />
                  <Skeleton className="h-3.5 w-12" />
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: `repeat(${HEATMAP_COLS}, 1fr)`,
                    gap: 3,
                  }}
                >
                  {Array.from({ length: 20 }).map((_, i) => (
                    <Skeleton key={i} className="aspect-square rounded-sm" />
                  ))}
                </div>
              </div>
            </SheetSection>
            <SheetSection>
              <div className="grid grid-cols-2 gap-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-18.25 rounded-md" />
                ))}
              </div>
            </SheetSection>
            <SheetSection className="flex-1">
              <div className="space-y-1.5">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} className="h-9 rounded-md" />
                ))}
              </div>
            </SheetSection>
          </>
        ) : profile ? (
          <>
            {/* Follow / Sub / Role / Ban status */}
            <SheetSection className="space-y-3">
              <StatusRow icon="fa-solid fa-heart" iconClass="text-status-follow">
                {profile.follow_since ? (
                  <span>
                    自 <span className="font-medium">{formatDateFull(profile.follow_since)}</span>{' '}
                    開始追隨
                  </span>
                ) : (
                  <span className="text-muted-foreground">尚未追隨</span>
                )}
              </StatusRow>
              {twitch?.is_subscribed ? (
                <StatusRow
                  role={channelBadges?.subscriber_1m ? 'subscriber' : undefined}
                  badgeSrc={channelBadges?.subscriber_1m ?? null}
                  icon="fa-solid fa-star"
                  iconClass="text-status-special"
                >
                  <span className="font-medium">
                    {SUB_TIER_LABEL[twitch.sub_tier ?? ''] ?? '訂閱中'}
                  </span>
                  {twitch.sub_gifted && (
                    <span className="ml-1 text-muted-foreground text-label">
                      {twitch.sub_gifter ? `・由 @${twitch.sub_gifter} 贈送` : '・贈禮訂閱'}
                    </span>
                  )}
                </StatusRow>
              ) : (
                <StatusRow icon="fa-regular fa-star" iconClass="text-muted-foreground">
                  <span className="text-muted-foreground">尚未訂閱</span>
                </StatusRow>
              )}
              {twitch?.is_mod && (
                <StatusRow role="moderator">
                  <span className="font-medium">頻道管理員</span>
                </StatusRow>
              )}
              {twitch?.is_vip && !twitch?.is_mod && (
                <StatusRow role="vip">
                  <span className="font-medium">VIP</span>
                </StatusRow>
              )}
              {twitch?.is_banned && (
                <StatusRow icon="fa-solid fa-ban" iconClass="text-destructive">
                  {twitch.ban_expires_at ? (
                    <span>
                      封禁至{' '}
                      <span className="font-medium">{formatDateFull(twitch.ban_expires_at)}</span>
                      {twitch.ban_reason && (
                        <span className="text-muted-foreground ml-1">（{twitch.ban_reason}）</span>
                      )}
                    </span>
                  ) : (
                    <span>
                      永久封禁
                      {twitch.ban_reason && (
                        <span className="text-muted-foreground ml-1">（{twitch.ban_reason}）</span>
                      )}
                    </span>
                  )}
                </StatusRow>
              )}
            </SheetSection>

            {/* Attendance heatmap */}
            {profile.session_attendance.length > 0 && (
              <SheetSection>
                <ViewerHeatmap
                  sessions={profile.session_attendance}
                  streakCount={profile.streak_count}
                  bestStreak={profile.best_streak}
                />
              </SheetSection>
            )}

            {/* Stats */}
            <SheetSection>
              <div className="grid grid-cols-2 gap-3">
                <StatTile
                  icon="fa-solid fa-diamond-half-stroke"
                  value={profile.total_bits > 0 ? formatCompact(profile.total_bits) : '—'}
                  label="小奇點"
                  tooltip={
                    profile.total_bits >= 1_000 ? profile.total_bits.toLocaleString() : undefined
                  }
                />
                <StatTile
                  icon="fa-solid fa-comments"
                  value={formatCompact(profile.total_messages)}
                  label="留言次數"
                  tooltip={
                    profile.total_messages >= 1_000
                      ? profile.total_messages.toLocaleString()
                      : undefined
                  }
                />
                <StatTile
                  icon="fa-solid fa-gift"
                  value={totalGifts > 0 ? totalGifts.toLocaleString() : '—'}
                  label="贈禮訂閱"
                />
                <StatTile
                  icon="fa-solid fa-clock"
                  value={profile.watch_seconds > 0 ? formatDuration(profile.watch_seconds) : '—'}
                  label="觀看時長"
                  tooltip={
                    profile.watch_seconds >= 3600
                      ? `${Math.floor(profile.watch_seconds / 60).toLocaleString()} 分鐘`
                      : undefined
                  }
                />
              </div>
              <div className="flex flex-col gap-y-1 mt-3">
                <p className="text-label text-muted-foreground">
                  最後活躍：{formatDateFull(profile.last_seen)}
                </p>
                {profile.account_created_at && (
                  <p className="text-label text-muted-foreground">
                    帳號建立：{formatDateFull(profile.account_created_at)}
                  </p>
                )}
              </div>
            </SheetSection>

            {/* Events */}
            {profile.events.length > 0 && (
              <SheetSection title="互動紀錄" className="flex-1">
                <div className="space-y-1.5">
                  {profile.events.map((ev, i) => {
                    const meta = EVENT_META[ev.event_type] ?? {
                      icon: 'fa-solid fa-circle-info',
                      label: ev.event_type,
                      color: 'text-muted-foreground',
                    }
                    const bits =
                      ev.event_type === 'cheer'
                        ? (ev.metadata as { bits?: number })?.bits
                        : undefined
                    const raidViewers =
                      ev.event_type === 'raid'
                        ? (ev.metadata as { viewers?: number; from_broadcaster_name?: string })
                        : undefined
                    const subMeta =
                      ev.event_type === 'subscribe'
                        ? (ev.metadata as {
                            tier?: string
                            is_gift?: boolean
                            gift_count?: number
                          } | null)
                        : undefined
                    const subTierLabel = subMeta?.tier
                      ? (SUB_TIER_LABEL[String(Number(subMeta.tier) / 1000)] ?? null)
                      : null
                    const isGift = subMeta?.is_gift === true
                    const giftCount = isGift ? (subMeta?.gift_count ?? null) : null
                    const rowIcon = isGift ? 'fa-solid fa-gift' : meta.icon
                    const rowColor = isGift ? 'text-status-special' : meta.color
                    const rowLabel = isGift ? '贈禮訂閱' : meta.label
                    return (
                      <div
                        key={`${i}-${ev.occurred_at}-${ev.event_type}`}
                        className="flex items-center gap-3 py-1.5"
                      >
                        <Icon icon={rowIcon} size="sm" wrapperClassName={`${rowColor} shrink-0`} />
                        <span className="text-sub flex-1 flex items-center gap-1.5">
                          {rowLabel}
                          {subTierLabel && (
                            <span className="text-muted-foreground">({subTierLabel})</span>
                          )}
                          {giftCount != null && (
                            <>
                              <span className="text-muted-foreground">×</span>
                              <span>{giftCount}</span>
                            </>
                          )}
                          {bits !== undefined && (
                            <>
                              <span className="text-muted-foreground">×</span>
                              <span>{bits.toLocaleString()} 小奇點</span>
                            </>
                          )}
                          {raidViewers?.viewers != null && (
                            <span className="text-muted-foreground">
                              ({raidViewers.viewers.toLocaleString()} 人)
                            </span>
                          )}
                        </span>
                        <span className="text-label text-muted-foreground shrink-0">
                          {formatDate(ev.occurred_at)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </SheetSection>
            )}
          </>
        ) : (
          <SheetSection>
            <p className="text-sub text-muted-foreground">無法載入觀眾資料</p>
          </SheetSection>
        )}
      </SheetContent>
    </Sheet>
  )
}
