import React from 'react'

import { type ViewerSessionAttendance } from '@/api/analytics'
import { Badge, Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui'

import { formatDate, formatDuration } from './utils'

type HeatmapFields = Pick<
  ViewerSessionAttendance,
  'attended' | 'stream_duration_seconds' | 'viewer_watch_seconds'
>

function watchPercent(s: HeatmapFields): number {
  if (!s.attended || !s.stream_duration_seconds || !s.viewer_watch_seconds) return 0
  return Math.min(100, Math.round((s.viewer_watch_seconds / s.stream_duration_seconds) * 100))
}

function heatmapOpacity(attended: boolean, pct: number): number {
  if (!attended) return 0.2
  if (pct === 0) return 0.25
  if (pct <= 25) return 0.42
  if (pct <= 50) return 0.6
  if (pct <= 75) return 0.8
  return 1
}

export const HEATMAP_COLS = 10

const LEGEND_DOTS: HeatmapFields[] = [
  { attended: false, stream_duration_seconds: 0, viewer_watch_seconds: 0 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 0 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 30 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 60 },
  { attended: true, stream_duration_seconds: 100, viewer_watch_seconds: 100 },
]

function HeatmapCell({ s }: { s: ViewerSessionAttendance }) {
  const pct = watchPercent(s)
  const watchLabel = formatDuration(s.viewer_watch_seconds)
  const dateLabel = formatDate(s.started_at)
  const ariaLabel = !s.attended
    ? `${dateLabel} 未出席`
    : pct > 0
      ? `${dateLabel} 觀看 ${watchLabel} (${pct}%)`
      : `${dateLabel} 出席`

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          role="img"
          aria-label={ariaLabel}
          className="aspect-square rounded-sm cursor-default hover:scale-125 transition-transform duration-fast ease-spring"
          style={{
            background: s.attended ? 'var(--primary)' : 'var(--muted-foreground)',
            opacity: heatmapOpacity(s.attended, pct),
          }}
        />
      </TooltipTrigger>
      <TooltipContent side="top">
        <p className="text-sub font-medium">{dateLabel}</p>
        {!s.attended ? (
          <p className="text-label opacity-70">未出席</p>
        ) : pct > 0 ? (
          <p className="text-label opacity-70">
            觀看 {watchLabel}
            <span className="ml-1 text-primary">({pct}%)</span>
          </p>
        ) : (
          <p className="text-label opacity-70">出席（無觀看紀錄）</p>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

export function ViewerHeatmap({
  sessions,
  streakCount,
  bestStreak,
}: {
  sessions: ViewerSessionAttendance[]
  streakCount?: number
  bestStreak?: number
}) {
  const attended = React.useMemo(() => sessions.filter(s => s.attended).length, [sessions])

  if (sessions.length === 0) return null

  const activeStreak = streakCount ?? 0
  const best = bestStreak ?? 0

  return (
    <TooltipProvider delayDuration={150}>
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <p className="text-label text-muted-foreground">出席紀錄</p>
            <p className="text-label text-muted-foreground/60">
              ({attended} / {sessions.length} 場)
            </p>
          </div>
          <div className="flex items-center gap-1.5">
            {activeStreak > 1 && (
              <Badge
                variant="outline"
                className="rounded-sm text-rank-gold border-rank-gold/30 bg-rank-gold/5 font-normal"
              >
                <i className="fa-solid fa-fire" />
                連續 {activeStreak} 場
              </Badge>
            )}
            {best > 1 && activeStreak <= 1 && (
              <Badge
                variant="outline"
                className="rounded-sm text-primary border-primary/30 bg-primary/5 font-normal"
              >
                <i className="fa-solid fa-trophy" />
                最高 {best} 場
              </Badge>
            )}
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${HEATMAP_COLS}, 1fr)`,
            gap: 3,
          }}
        >
          {sessions.map(s => (
            <HeatmapCell key={s.session_id} s={s} />
          ))}
        </div>

        <div className="flex items-center gap-2 self-end">
          <span className="text-label text-muted-foreground/50">未出席</span>
          <div className="flex gap-0.5">
            {LEGEND_DOTS.map((d, i) => (
              <div
                key={i}
                className="w-2.5 h-2.5 rounded-sm"
                style={{
                  background: d.attended ? 'var(--primary)' : 'var(--muted-foreground)',
                  opacity: heatmapOpacity(d.attended, watchPercent(d)),
                }}
              />
            ))}
          </div>
          <span className="text-label text-muted-foreground/50">100%</span>
        </div>
      </div>
    </TooltipProvider>
  )
}
