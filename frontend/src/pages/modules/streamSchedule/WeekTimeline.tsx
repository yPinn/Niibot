import { useEffect, useState } from 'react'

import {
  getStreamScheduleSegments,
  type ScheduleKind,
  type StreamSchedule,
  type StreamScheduleSegment,
} from '@/api/streamSchedule'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import {
  isLiveNow,
  resolveContinuationForDate,
  resolveScheduleForDate,
  timeStrToMinutes,
  toDateStr,
  weekdayOf,
} from './calendar'
import { WEEKDAY_LABELS } from './constants'
import { endTimeFor } from './time'

const LEFT_COL_WIDTH = 88
const ROW_HEIGHT = 64
const MINUTES_PER_DAY = 1440

interface WeekTimelineProps {
  days: Date[] // exactly 7, Sunday first
  schedules: StreamSchedule[]
  onEditSchedule: (schedule: StreamSchedule) => void
  onCreateForDate: (dateStr: string) => void
}

function formatHourLabel(hour: number): string {
  return `${String(hour).padStart(2, '0')}:00`
}

function formatMinutesLabel(minutes: number): string {
  return `${String(Math.floor(minutes / 60)).padStart(2, '0')}:${String(minutes % 60).padStart(2, '0')}`
}

/** Percentage of the 24h track, not pixels — the hour columns auto-divide to
 * fill whatever width is available instead of a fixed per-hour pixel width,
 * so block position/size need to scale the same way. */
function xForMinutes(minutes: number): number {
  return (minutes / MINUTES_PER_DAY) * 100
}

/** One color per schedule kind, applied identically everywhere a schedule's
 * block appears (main block, its continuation, live or not) — a schedule
 * spanning midnight is one event, not two, so it shouldn't change hue
 * depending on which row-portion is showing or whether it's airing this
 * instant. "Live" is communicated by the bold "正在開台" label instead. */
function blockColorClass(kind: ScheduleKind): string {
  return kind === 'one_off'
    ? 'bg-primary/15 text-primary'
    : 'bg-secondary text-secondary-foreground'
}

/** Which segment is currently in effect, elapsedMinutes after the schedule's
 * own start — the same "latest offset not in the future" rule the backend's
 * real resolver uses, so a live block shows what's actually airing right now
 * instead of just the schedule's base title (segments can override it
 * mid-stream). */
function resolveActiveSegment(
  segments: StreamScheduleSegment[],
  elapsedMinutes: number
): StreamScheduleSegment | null {
  let active: StreamScheduleSegment | null = null
  for (const seg of segments) {
    if (
      seg.offset_minutes <= elapsedMinutes &&
      (!active || seg.offset_minutes > active.offset_minutes)
    ) {
      active = seg
    }
  }
  return active
}

/** Segment breakdown (title/category per offset) isn't loaded with the
 * schedule list the calendar already has — fetching it for every visible
 * schedule up front would be wasted work most of the time, so each row
 * fetches its own on first hover instead. No cross-hover cache: segments can
 * be edited from the same sheet this calendar opens, so refetching per mount
 * (rather than risking a stale cache) is the simpler correct choice — hover
 * is infrequent enough that this costs nothing noticeable. */
function useSegmentPreview(scheduleId: number | null) {
  const [state, setState] = useState<{ id: number; segments: StreamScheduleSegment[] } | null>(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    if (scheduleId === null || loading || state?.id === scheduleId) return
    setLoading(true)
    getStreamScheduleSegments(scheduleId)
      .then(data => setState({ id: scheduleId, segments: data }))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  return { segments: state?.id === scheduleId ? state.segments : null, loading, load }
}

interface SchedulePreviewProps {
  schedule: StreamSchedule
  segments: StreamScheduleSegment[] | null
  loading: boolean
}

function SchedulePreview({ schedule, segments, loading }: SchedulePreviewProps) {
  const start = schedule.start_time.slice(0, 5)
  return (
    <div className="flex flex-col gap-1">
      <div className="font-medium">{schedule.title_template || '（未設定標題）'}</div>
      <div className="text-muted-foreground">
        {start}–{endTimeFor(start, schedule.duration_minutes)}
      </div>
      {loading ? (
        <div className="text-muted-foreground">載入分段中…</div>
      ) : segments && segments.length > 0 ? (
        <div className="flex flex-col gap-0.5 border-t border-border pt-1">
          {segments.map(seg => (
            <div key={seg.id} className="text-muted-foreground">
              {endTimeFor(start, seg.offset_minutes)}
              {seg.offset_minutes === 0 && '（開台）'} {seg.game_name || '（未設定分類）'}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}

interface BlockContentProps {
  isLive: boolean
  fallbackTitle: string
  fallbackSubtitle: string
  activeSegment: StreamScheduleSegment | null
}

/** Line 2 is the title, line 3 the category — for a live block these come
 * from whichever segment is currently active (falling back to the
 * schedule's own fields once segments have loaded but none apply yet, or
 * while they're still loading); a non-live block just shows its normal
 * summary. */
function BlockContent({
  isLive,
  fallbackTitle,
  fallbackSubtitle,
  activeSegment,
}: BlockContentProps) {
  const title = (isLive && activeSegment?.title_template) || fallbackTitle
  const subtitle = (isLive && activeSegment?.game_name) || fallbackSubtitle
  return (
    <>
      {isLive && <div className="font-bold">正在開台</div>}
      <div className="truncate font-medium">{title}</div>
      <div className="truncate text-muted-foreground">{subtitle}</div>
    </>
  )
}

interface WeekDayRowProps {
  day: Date
  schedules: StreamSchedule[]
  today: string
  now: Date
  nowX: number
  onEditSchedule: (schedule: StreamSchedule) => void
  onCreateForDate: (dateStr: string) => void
}

function WeekDayRow({
  day,
  schedules,
  today,
  now,
  nowX,
  onEditSchedule,
  onCreateForDate,
}: WeekDayRowProps) {
  const dateStr = toDateStr(day)
  const resolved = resolveScheduleForDate(schedules, dateStr)
  const isToday = dateStr === today
  const live = resolved ? isLiveNow(resolved, dateStr, now) : false

  const startMinutes = resolved ? timeStrToMinutes(resolved.start_time) : 0
  const visibleMinutes = resolved
    ? Math.min(resolved.duration_minutes, MINUTES_PER_DAY - startMinutes)
    : 0

  const continuation = resolveContinuationForDate(schedules, dateStr)
  const continuationLive =
    continuation !== null &&
    isToday &&
    now.getHours() * 60 + now.getMinutes() < continuation.minutes

  const resolvedPreview = useSegmentPreview(resolved?.id ?? null)
  const continuationPreview = useSegmentPreview(continuation?.schedule.id ?? null)

  // A live block's on-screen text needs segment data immediately (to show
  // what's actually airing right now), not just on hover like the tooltip —
  // cheap since at most today's row can ever be live.
  useEffect(() => {
    if (live) resolvedPreview.load()
    if (continuationLive) continuationPreview.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [live, continuationLive])

  const resolvedActiveSegment = live
    ? resolveActiveSegment(
        resolvedPreview.segments ?? [],
        now.getHours() * 60 + now.getMinutes() - startMinutes
      )
    : null
  const continuationActiveSegment =
    continuationLive && continuation
      ? resolveActiveSegment(
          continuationPreview.segments ?? [],
          MINUTES_PER_DAY -
            timeStrToMinutes(continuation.schedule.start_time) +
            (now.getHours() * 60 + now.getMinutes())
        )
      : null

  const baseLabel = resolved
    ? `${dateStr}：${resolved.start_time.slice(0, 5)} ${resolved.title_template || '（已排程）'}${live ? '，正在開台' : ''}`
    : `${dateStr}：尚未排程`
  const continuationLabel = continuation
    ? `；延續自昨晚，播到 ${formatMinutesLabel(continuation.minutes)}${continuationLive ? '，正在開台' : ''}`
    : ''

  return (
    <button
      type="button"
      onClick={() => (resolved ? onEditSchedule(resolved) : onCreateForDate(dateStr))}
      aria-label={baseLabel + continuationLabel}
      className="flex w-full border-b border-border text-left last:border-b-0 hover:bg-accent/40"
    >
      <div
        style={{ width: LEFT_COL_WIDTH }}
        className={cn(
          'shrink-0 border-r border-border p-2 text-sub',
          isToday && 'font-bold text-primary'
        )}
      >
        <div>{WEEKDAY_LABELS[weekdayOf(day)]}</div>
        <div className="text-label text-muted-foreground">
          {day.getMonth() + 1}/{day.getDate()}
        </div>
      </div>

      <div className="relative flex-1" style={{ height: ROW_HEIGHT }}>
        <div className="absolute inset-0 flex">
          {Array.from({ length: 24 }, (_, h) => (
            <div key={h} className="flex-1 border-r border-border/20" />
          ))}
        </div>

        {isToday && (
          <div
            className="absolute top-0 bottom-0 w-px bg-destructive"
            style={{ left: `${nowX}%` }}
          />
        )}

        {continuation && (
          <Tooltip onOpenChange={open => open && continuationPreview.load()}>
            <TooltipTrigger asChild>
              <div
                className={cn(
                  'absolute top-1 bottom-1 overflow-hidden rounded-r px-2 py-1 text-label leading-tight',
                  blockColorClass(continuation.schedule.kind)
                )}
                style={{ left: 0, width: `${xForMinutes(continuation.minutes)}%` }}
              >
                <BlockContent
                  isLive={continuationLive}
                  fallbackTitle={
                    continuation.schedule.title_template ||
                    `延續至 ${formatMinutesLabel(continuation.minutes)}`
                  }
                  fallbackSubtitle={`延續至 ${formatMinutesLabel(continuation.minutes)}`}
                  activeSegment={continuationActiveSegment}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <SchedulePreview
                schedule={continuation.schedule}
                segments={continuationPreview.segments}
                loading={continuationPreview.loading}
              />
            </TooltipContent>
          </Tooltip>
        )}

        {resolved && (
          <Tooltip onOpenChange={open => open && resolvedPreview.load()}>
            <TooltipTrigger asChild>
              <div
                className={cn(
                  'absolute top-1 bottom-1 overflow-hidden rounded px-2 py-1 text-label leading-tight',
                  blockColorClass(resolved.kind)
                )}
                style={{
                  left: `${xForMinutes(startMinutes)}%`,
                  width: `${xForMinutes(visibleMinutes)}%`,
                }}
              >
                <BlockContent
                  isLive={live}
                  fallbackTitle={resolved.title_template || resolved.start_time.slice(0, 5)}
                  fallbackSubtitle={resolved.start_time.slice(0, 5)}
                  activeSegment={resolvedActiveSegment}
                />
              </div>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              <SchedulePreview
                schedule={resolved}
                segments={resolvedPreview.segments}
                loading={resolvedPreview.loading}
              />
            </TooltipContent>
          </Tooltip>
        )}
      </div>
    </button>
  )
}

/** Twitch-style hourly Gantt timeline: one row per day, entries positioned
 * horizontally by time-of-day instead of Google-Calendar-style stacked cells.
 * Only shows the day-level resolved schedule (see calendar.ts) — segment-level
 * sub-blocks within a schedule aren't fetched at this view, same scope
 * boundary the month/list views already use (segment detail is available on
 * hover instead, see useSegmentPreview above). */
export function WeekTimeline({
  days,
  schedules,
  onEditSchedule,
  onCreateForDate,
}: WeekTimelineProps) {
  const now = new Date()
  const today = toDateStr(now)
  const nowX = xForMinutes(now.getHours() * 60 + now.getMinutes())

  return (
    <div className="rounded-md border border-border">
      <div className="flex border-b border-border bg-muted/30">
        <div
          style={{ width: LEFT_COL_WIDTH }}
          className="shrink-0 border-r border-border p-2 text-label text-muted-foreground"
        >
          GMT+8
        </div>
        {Array.from({ length: 24 }, (_, h) => (
          <div
            key={h}
            className="flex-1 overflow-hidden border-r border-border/40 py-2 text-center text-label whitespace-nowrap text-muted-foreground"
          >
            {formatHourLabel(h)}
          </div>
        ))}
      </div>

      {days.map(day => (
        <WeekDayRow
          key={toDateStr(day)}
          day={day}
          schedules={schedules}
          today={today}
          now={now}
          nowX={nowX}
          onEditSchedule={onEditSchedule}
          onCreateForDate={onCreateForDate}
        />
      ))}
    </div>
  )
}
