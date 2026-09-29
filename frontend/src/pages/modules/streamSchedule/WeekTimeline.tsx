import { useEffect, useRef, useState } from 'react'

import type {
  StreamSchedule,
  StreamScheduleOccurrenceException,
  StreamScheduleSegment,
} from '@/api/streamSchedule'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import {
  cancelledSchedulesForDate,
  firstSegment,
  isLiveNow,
  minutesInTimeZone,
  resolveActiveSegment,
  resolveContinuationForDate,
  resolveSchedulesForDate,
  timeStrToMinutes,
  timeZoneOffsetLabel,
  toDateStr,
  weekdayOf,
} from './calendar'
import { scheduleBlockClass, WEEKDAY_LABELS } from './constants'
import { useGameColor } from './gameColor'
import { SchedulePreview } from './schedulePreview'
import { useSegmentPreview } from './useSegmentPreview'

const LEFT_COL_WIDTH = 128
const ROW_HEIGHT = 64
const MINUTES_PER_DAY = 1440
// A fixed 24 one-hour columns doesn't fit every viewport — flex items won't
// actually shrink below their text's intrinsic width without min-w-0, so
// cramming 24 five-character labels into too little space corrupts the
// layout instead of just looking cramped. Grouping into coarser buckets
// (4h/6h/etc.) when space is tight avoids that outright, rather than
// patching around it with ever-smaller text.
const MIN_COLUMN_PX = 44
const HOUR_GROUPINGS = [1, 2, 3, 4, 6, 8, 12] as const

function pickHoursPerColumn(trackWidthPx: number): number {
  for (const hours of HOUR_GROUPINGS) {
    if (trackWidthPx / (24 / hours) >= MIN_COLUMN_PX) return hours
  }
  return HOUR_GROUPINGS[HOUR_GROUPINGS.length - 1]
}

/** Measures a ref'd element's width, re-measuring on resize (sidebar
 * collapse, window resize, zoom) — not just at mount. */
function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)

  useEffect(() => {
    const el = ref.current
    if (!el || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(entries => {
      const entry = entries[0]
      if (entry) setWidth(entry.contentRect.width)
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  return { ref, width }
}

interface WeekTimelineProps {
  days: Date[] // exactly 7, Sunday first
  schedules: StreamSchedule[]
  exceptions: StreamScheduleOccurrenceException[]
  timezone: string
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
  onCreateForDate: (dateStr: string) => void
  onRestoreOccurrence: (schedule: StreamSchedule, dateStr: string) => void
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

interface BlockContentProps {
  isLive: boolean
  fallbackTitle: string
  fallbackSubtitle: string
  activeSegment: StreamScheduleSegment | null
  defaultSegment: StreamScheduleSegment | null
  colored: boolean
}

/** Line 2 is the title, line 3 the category — matching Twitch's own schedule
 * page, every block shows both, not just the one currently airing. A live
 * block uses whichever segment is currently active (segments can override
 * the schedule's base title/category mid-stream); a non-live block uses the
 * earliest segment instead, since that's what go-live will actually apply.
 * Both fall back to the schedule's own fields while segments are still
 * loading or if none are set up. `colored` is true once a game-derived
 * background is in use — the block's own text-white then needs the
 * subtitle line to follow it too, instead of the fixed muted-foreground
 * token that assumes the kind-based background. */
function BlockContent({
  isLive,
  fallbackTitle,
  fallbackSubtitle,
  activeSegment,
  defaultSegment,
  colored,
}: BlockContentProps) {
  const segment = isLive ? activeSegment : defaultSegment
  const title = segment?.title_template || fallbackTitle
  const subtitle = segment?.game_name || fallbackSubtitle
  return (
    <>
      {isLive && <div className="font-bold">正在開台</div>}
      <div className="truncate font-medium">{title}</div>
      <div className={cn('truncate', colored ? 'text-white/85' : 'text-muted-foreground')}>
        {subtitle}
      </div>
    </>
  )
}

interface WeekDayRowProps {
  day: Date
  schedules: StreamSchedule[]
  exceptions: StreamScheduleOccurrenceException[]
  today: string
  now: Date
  nowX: number
  columnCount: number
  timezone: string
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
  onCreateForDate: (dateStr: string) => void
  onRestoreOccurrence: (schedule: StreamSchedule, dateStr: string) => void
}

function WeekScheduleBlock({
  schedule,
  dateStr,
  now,
  timezone,
  isReplacement,
  onEditSchedule,
}: {
  schedule: StreamSchedule
  dateStr: string
  now: Date
  timezone: string
  isReplacement: boolean
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
}) {
  const live = isLiveNow(schedule, dateStr, now, timezone)
  const startMinutes = timeStrToMinutes(schedule.start_time)
  const visibleMinutes = Math.min(schedule.duration_minutes, MINUTES_PER_DAY - startMinutes)
  const preview = useSegmentPreview(schedule.id)
  useEffect(() => {
    preview.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schedule.id])
  const activeSegment = live
    ? resolveActiveSegment(preview.segments ?? [], minutesInTimeZone(now, timezone) - startMinutes)
    : null
  const defaultSegment = firstSegment(preview.segments ?? [])
  const effectiveSegment = live ? activeSegment : defaultSegment
  const gameColor = useGameColor(
    effectiveSegment?.game_id ?? null,
    effectiveSegment?.game_name ?? null
  )

  return (
    <Tooltip onOpenChange={open => open && preview.load()}>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => onEditSchedule(schedule, dateStr)}
          aria-label={`${dateStr}：${schedule.start_time.slice(0, 5)} ${schedule.title_template || '（已排程）'}${live ? '，正在開台' : ''}`}
          className={cn(
            'absolute top-1 bottom-1 z-10 select-none overflow-hidden rounded px-2 py-1 text-left text-label leading-tight',
            gameColor ? 'text-white' : scheduleBlockClass(schedule.kind)
          )}
          style={{
            left: `${xForMinutes(startMinutes)}%`,
            width: `${xForMinutes(visibleMinutes)}%`,
            ...(gameColor && { background: gameColor }),
          }}
        >
          <BlockContent
            isLive={live}
            fallbackTitle={schedule.title_template || schedule.start_time.slice(0, 5)}
            fallbackSubtitle={isReplacement ? '本次調整' : schedule.start_time.slice(0, 5)}
            activeSegment={activeSegment}
            defaultSegment={defaultSegment}
            colored={!!gameColor}
          />
        </button>
      </TooltipTrigger>
      <TooltipContent side="bottom">
        <SchedulePreview
          schedule={schedule}
          segments={preview.segments}
          loading={preview.loading}
        />
      </TooltipContent>
    </Tooltip>
  )
}

function WeekDayRow({
  day,
  schedules,
  exceptions,
  today,
  now,
  nowX,
  columnCount,
  timezone,
  onEditSchedule,
  onCreateForDate,
  onRestoreOccurrence,
}: WeekDayRowProps) {
  const dateStr = toDateStr(day)
  const resolved = resolveSchedulesForDate(schedules, dateStr, timezone, exceptions)
  const cancelled = cancelledSchedulesForDate(schedules, dateStr, exceptions)
  const replacementIds = new Set(
    exceptions
      .filter(exception => exception.occurrence_date === dateStr)
      .map(exception => exception.replacement_schedule_id)
  )
  const isToday = dateStr === today
  const nowMinutes = minutesInTimeZone(now, timezone)
  const continuation = resolveContinuationForDate(schedules, dateStr, timezone, exceptions)
  const continuationLive = continuation !== null && isToday && nowMinutes < continuation.minutes
  const continuationPreview = useSegmentPreview(continuation?.schedule.id ?? null)
  useEffect(() => {
    continuationPreview.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [continuation?.schedule.id])
  const continuationActiveSegment =
    continuationLive && continuation
      ? resolveActiveSegment(
          continuationPreview.segments ?? [],
          MINUTES_PER_DAY - timeStrToMinutes(continuation.schedule.start_time) + nowMinutes
        )
      : null
  const continuationDefaultSegment = firstSegment(continuationPreview.segments ?? [])
  const continuationEffectiveSegment = continuationLive
    ? continuationActiveSegment
    : continuationDefaultSegment
  const continuationGameColor = useGameColor(
    continuationEffectiveSegment?.game_id ?? null,
    continuationEffectiveSegment?.game_name ?? null
  )

  return (
    <div className="flex w-full border-b border-border text-left last:border-b-0 hover:bg-accent/40">
      <div
        style={{ width: LEFT_COL_WIDTH }}
        className={cn(
          'flex shrink-0 flex-col items-center justify-center border-r border-border p-2 text-center text-sub',
          isToday && 'font-bold text-primary'
        )}
      >
        <div>{WEEKDAY_LABELS[weekdayOf(day)]}</div>
        <div className="text-label text-muted-foreground">
          {day.getUTCMonth() + 1}/{day.getUTCDate()}
        </div>
      </div>

      <div className="relative min-w-0 flex-1" style={{ height: ROW_HEIGHT }}>
        <button
          type="button"
          className="absolute inset-0 select-none"
          onClick={() => onCreateForDate(dateStr)}
          aria-label={resolved.length === 0 ? `${dateStr}：尚未排程` : `新增 ${dateStr} 排程`}
        />
        <div className="pointer-events-none absolute inset-0 flex">
          {Array.from({ length: columnCount }, (_, h) => (
            <div key={h} className="min-w-0 flex-1 border-r border-border/20" />
          ))}
        </div>
        {isToday && (
          <div
            className="pointer-events-none absolute top-0 bottom-0 w-px bg-destructive"
            style={{ left: `${nowX}%` }}
          />
        )}
        {continuation && (
          <Tooltip onOpenChange={open => open && continuationPreview.load()}>
            <TooltipTrigger asChild>
              <div
                className={cn(
                  'absolute top-1 bottom-1 z-10 overflow-hidden rounded-r px-2 py-1 text-label leading-tight',
                  continuationGameColor
                    ? 'text-white'
                    : scheduleBlockClass(continuation.schedule.kind)
                )}
                style={{
                  left: 0,
                  width: `${xForMinutes(continuation.minutes)}%`,
                  ...(continuationGameColor && { background: continuationGameColor }),
                }}
              >
                <BlockContent
                  isLive={continuationLive}
                  fallbackTitle={
                    continuation.schedule.title_template ||
                    `延續至 ${formatMinutesLabel(continuation.minutes)}`
                  }
                  fallbackSubtitle={`延續至 ${formatMinutesLabel(continuation.minutes)}`}
                  activeSegment={continuationActiveSegment}
                  defaultSegment={continuationDefaultSegment}
                  colored={!!continuationGameColor}
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
        {resolved.map(schedule => (
          <WeekScheduleBlock
            key={schedule.id}
            schedule={schedule}
            dateStr={dateStr}
            now={now}
            timezone={timezone}
            isReplacement={replacementIds.has(schedule.id)}
            onEditSchedule={onEditSchedule}
          />
        ))}
        {cancelled.map(schedule => {
          const startMinutes = timeStrToMinutes(schedule.start_time)
          const visibleMinutes = Math.min(schedule.duration_minutes, MINUTES_PER_DAY - startMinutes)
          return (
            <button
              key={`cancelled-${schedule.id}`}
              type="button"
              onClick={() => onRestoreOccurrence(schedule, dateStr)}
              aria-label={`${dateStr}：已取消，點擊恢復`}
              className="absolute top-1 bottom-1 z-10 select-none overflow-hidden rounded border border-dashed border-border bg-muted px-2 text-left text-label text-muted-foreground line-through"
              style={{
                left: `${xForMinutes(startMinutes)}%`,
                width: `${xForMinutes(visibleMinutes)}%`,
              }}
            >
              已取消
            </button>
          )
        })}
      </div>
    </div>
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
  exceptions,
  timezone,
  onEditSchedule,
  onCreateForDate,
  onRestoreOccurrence,
}: WeekTimelineProps) {
  const now = new Date()
  const today = new Intl.DateTimeFormat('en-CA', {
    timeZone: timezone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(now)
  const nowX = xForMinutes(minutesInTimeZone(now, timezone))
  const offset = timeZoneOffsetLabel(timezone, now)

  const { ref, width } = useElementWidth<HTMLDivElement>()
  const trackWidth = Math.max(width - LEFT_COL_WIDTH, 0)
  // Before the first measurement (width is 0), default to the finest
  // grouping rather than the coarsest — avoids a visible flash of 2-hour
  // buckets on a normal-width screen before ResizeObserver reports in.
  const hoursPerColumn = width === 0 ? 1 : pickHoursPerColumn(trackWidth)
  const columnCount = 24 / hoursPerColumn

  return (
    <div ref={ref} className="rounded-md border border-border">
      <div className="flex border-b border-border bg-muted/30">
        <div
          style={{ width: LEFT_COL_WIDTH }}
          className="flex shrink-0 items-center justify-center border-r border-border p-2 text-center text-label text-muted-foreground"
        >
          <span className="truncate" title={offset}>
            {offset}
          </span>
        </div>
        {Array.from({ length: columnCount }, (_, i) => (
          <div
            key={i}
            className="min-w-0 flex-1 overflow-hidden border-r border-border/40 py-2 text-center text-label whitespace-nowrap text-muted-foreground"
          >
            {formatHourLabel(i * hoursPerColumn)}
          </div>
        ))}
      </div>

      {days.map(day => (
        <WeekDayRow
          key={toDateStr(day)}
          day={day}
          schedules={schedules}
          exceptions={exceptions}
          today={today}
          now={now}
          nowX={nowX}
          columnCount={columnCount}
          timezone={timezone}
          onEditSchedule={onEditSchedule}
          onCreateForDate={onCreateForDate}
          onRestoreOccurrence={onRestoreOccurrence}
        />
      ))}
    </div>
  )
}
