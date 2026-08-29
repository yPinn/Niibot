import React from 'react'

import { type ChannelBadges, type ViewerSummary } from '@/api/analytics'
import { EmptyState, Icon, TwitchBadgeGroup } from '@/components/primitives'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import { SORT_COLS, type SortKey } from './types'
import { buildViewerBadges, formatDuration } from './utils'

const ROW_GRID = 'grid-cols-[1.25rem_minmax(0,1fr)_5.5rem_5.5rem_5.5rem]'

const RANK_STYLES = {
  1: {
    gradient: 'bg-gradient-to-r from-rank-gold/15',
    border: 'border-rank-gold/30',
    icon: 'fa-solid fa-trophy',
    color: 'text-rank-gold',
  },
  2: {
    gradient: 'bg-gradient-to-r from-rank-silver/15',
    border: 'border-rank-silver/30',
    icon: 'fa-solid fa-medal',
    color: 'text-rank-silver',
  },
  3: {
    gradient: 'bg-gradient-to-r from-rank-bronze/15',
    border: 'border-rank-bronze/30',
    icon: 'fa-solid fa-medal',
    color: 'text-rank-bronze',
  },
} as const

interface ViewerRowProps {
  viewer: ViewerSummary
  rank: number
  isHovered: boolean
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
  channelBadges: ChannelBadges | null
}

export interface ViewerListProps {
  filtered: ViewerSummary[]
  rankMap: Map<string, number>
  sort: SortKey
  sortDir: 'desc' | 'asc'
  search: string
  hoveredUserId: string | null
  channelBadges: ChannelBadges | null
  onSort: (key: SortKey) => void
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
}

function Col({
  value,
  valueClassName,
  className,
}: {
  value: string
  valueClassName?: string
  className?: string
}) {
  return (
    <div className={`text-right ${className ?? ''}`}>
      <p className={`text-sub font-bold tabular-nums ${valueClassName ?? ''}`}>{value}</p>
    </div>
  )
}

const ViewerRow = React.memo(function ViewerRow({
  viewer,
  rank,
  isHovered,
  onSelect,
  onHover,
  channelBadges,
}: ViewerRowProps) {
  const name = viewer.display_name || viewer.username
  const top = rank <= 3 ? RANK_STYLES[rank as 1 | 2 | 3] : null
  return (
    <button
      onClick={() => onSelect(viewer.user_id)}
      onMouseEnter={() => onHover(viewer.user_id)}
      onMouseLeave={() => onHover(null)}
      className={cn(
        'w-full grid items-center gap-3 rounded-md border px-3 py-2 hover:bg-accent transition-colors text-left',
        ROW_GRID,
        top && `${top.gradient} ${top.border}`,
        isHovered && 'ring-1 ring-inset ring-primary/40'
      )}
    >
      {top ? (
        <Icon icon={top.icon} className="text-label" wrapperClassName={top.color} />
      ) : (
        <span className="text-sub font-mono font-semibold text-muted-foreground text-right">
          {rank}
        </span>
      )}
      <div className="min-w-0">
        <div className="flex items-center gap-1.5 min-w-0">
          <TwitchBadgeGroup badges={buildViewerBadges(viewer, channelBadges)} />
          <p className="text-content font-medium truncate">{name}</p>
        </div>
        <p className="text-label text-muted-foreground truncate">@{viewer.username}</p>
      </div>
      <Col value={viewer.total_messages.toLocaleString()} />
      <Col value={formatDuration(viewer.watch_seconds)} />
      <Col value={viewer.engagement_score.toFixed(1)} valueClassName="text-primary" />
    </button>
  )
})

export function ViewerList({
  filtered,
  rankMap,
  sort,
  sortDir,
  search,
  hoveredUserId,
  channelBadges,
  onSort,
  onSelect,
  onHover,
}: ViewerListProps) {
  if (filtered.length === 0) {
    return (
      <EmptyState
        className="lg:flex-1"
        icon={search ? 'fa-solid fa-magnifying-glass' : 'fa-solid fa-users'}
        title={search ? '找不到符合的觀眾' : '尚無觀眾資料'}
        description={search ? undefined : '每場直播結束後會累積觀眾資料，歷史紀錄可在此查閱'}
      />
    )
  }
  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div
        className={`grid items-center gap-3 px-3 py-3 border border-transparent text-label text-muted-foreground shrink-0 ${ROW_GRID}`}
      >
        <span />
        <span>觀眾</span>
        {SORT_COLS.map(col => {
          const active = sort === col.key
          const btn = (
            <button
              type="button"
              onClick={() => onSort(col.key)}
              aria-sort={active ? (sortDir === 'desc' ? 'descending' : 'ascending') : 'none'}
              className={cn(
                'flex items-center justify-end gap-1 rounded pl-1 pr-0 py-0.5 transition-colors',
                active ? 'text-foreground font-medium' : 'hover:text-foreground'
              )}
            >
              <Icon icon={col.icon} size="xs" />
              {col.label}
              <Icon
                icon={`fa-solid ${active ? (sortDir === 'desc' ? 'fa-arrow-down' : 'fa-arrow-up') : 'fa-sort'}`}
                size="xs"
                className={cn('transition-opacity', active ? 'opacity-100' : 'opacity-30')}
              />
            </button>
          )
          if (col.key !== 'score') return <React.Fragment key={col.key}>{btn}</React.Fragment>
          return (
            <TooltipProvider key={col.key} delayDuration={200}>
              <Tooltip>
                <TooltipTrigger asChild>{btn}</TooltipTrigger>
                <TooltipContent className="max-w-52 text-center">
                  觀看時長＋留言活躍度＋訂閱／Cheer 小奇點加成，連續出席享乘數加成
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          )
        })}
      </div>
      <div className="flex flex-col gap-1 overflow-y-auto flex-1 min-h-0">
        {filtered.map((v, i) => {
          const rank = rankMap.get(v.user_id) ?? filtered.length + 1
          const showLowDivider =
            sort === 'score' &&
            sortDir === 'desc' &&
            v.engagement_score < 10 &&
            (i === 0 || filtered[i - 1].engagement_score >= 10)
          return (
            <React.Fragment key={v.user_id}>
              {showLowDivider && (
                <div className="flex items-center gap-2 px-1 py-1.5">
                  <div className="flex-1 h-px bg-border" />
                  <span className="text-label text-muted-foreground/50 shrink-0">低活躍</span>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}
              <ViewerRow
                viewer={v}
                rank={rank}
                isHovered={hoveredUserId === v.user_id}
                onSelect={onSelect}
                onHover={onHover}
                channelBadges={channelBadges}
              />
            </React.Fragment>
          )
        })}
      </div>
    </div>
  )
}
