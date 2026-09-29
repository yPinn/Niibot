import { useEffect, useMemo, useState } from 'react'

import type { StreamSchedule, StreamScheduleOccurrenceException } from '@/api/streamSchedule'
import { Icon } from '@/components/primitives'
import { Button, Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import {
  addDays,
  calendarDate,
  cancelledSchedulesForDate,
  firstSegment,
  monthGridWeekCount,
  resolveSchedulesForDate,
  startOfMonthGrid,
  startOfWeek,
  toDateStr,
  todayInTimeZone,
} from './calendar'
import { scheduleBlockClass, WEEK_DISPLAY_ORDER, WEEKDAY_LABELS } from './constants'
import { useGameColor } from './gameColor'
import { SchedulePreview } from './schedulePreview'
import { useSegmentPreview } from './useSegmentPreview'
import { WeekTimeline } from './WeekTimeline'

export type CalendarViewMode = 'week' | 'month'

interface CalendarViewProps {
  schedules: StreamSchedule[]
  exceptions: StreamScheduleOccurrenceException[]
  timezone: string
  mode: CalendarViewMode
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
  onCreateForDate: (dateStr: string) => void
  onRestoreOccurrence: (schedule: StreamSchedule, dateStr: string) => void
}

function addMonths(date: Date, delta: number): Date {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + delta, 1))
}

interface MonthDayCellProps {
  day: Date
  schedules: StreamSchedule[]
  exceptions: StreamScheduleOccurrenceException[]
  timezone: string
  isToday: boolean
  inCurrentMonth: boolean
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
  onCreateForDate: (dateStr: string) => void
  onRestoreOccurrence: (schedule: StreamSchedule, dateStr: string) => void
}

function MonthScheduleChip({
  schedule,
  dateStr,
  isReplacement,
  onEditSchedule,
}: {
  schedule: StreamSchedule
  dateStr: string
  isReplacement: boolean
  onEditSchedule: (schedule: StreamSchedule, dateStr: string) => void
}) {
  const preview = useSegmentPreview(schedule.id)
  useEffect(() => {
    preview.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schedule.id])
  const defaultSegment = firstSegment(preview.segments ?? [])
  const gameColor = useGameColor(defaultSegment?.game_id ?? null, defaultSegment?.game_name ?? null)

  return (
    <Tooltip onOpenChange={open => open && preview.load()}>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => onEditSchedule(schedule, dateStr)}
          aria-label={`${dateStr}：${schedule.start_time.slice(0, 5)} ${schedule.title_template || '（已排程）'}`}
          className={cn(
            'w-full min-w-0 select-none rounded px-1.5 py-1 text-left text-label leading-tight',
            gameColor ? 'text-white' : scheduleBlockClass(schedule.kind)
          )}
          style={gameColor ? { background: gameColor } : undefined}
        >
          <div className="font-medium">
            {schedule.start_time.slice(0, 5)}
            {isReplacement ? ' · 本次調整' : ''}
          </div>
          {schedule.title_template && <div className="truncate">{schedule.title_template}</div>}
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

/** Same treatment as the week timeline's blocks — game-derived color and a
 * hover tooltip with the full breakdown — so a schedule looks and behaves
 * consistently whether you're looking at it in week or month view. Only the
 * earliest segment is used here (no live/current-segment distinction like
 * the week view has); month is a birds-eye overview, not a live-tracking
 * surface. */
function MonthDayCell({
  day,
  schedules,
  exceptions,
  timezone,
  isToday,
  inCurrentMonth,
  onEditSchedule,
  onCreateForDate,
  onRestoreOccurrence,
}: MonthDayCellProps) {
  const dateStr = toDateStr(day)
  const resolved = resolveSchedulesForDate(schedules, dateStr, timezone, exceptions)
  const cancelled = cancelledSchedulesForDate(schedules, dateStr, exceptions)
  const replacementIds = new Set(
    exceptions
      .filter(exception => exception.occurrence_date === dateStr)
      .map(exception => exception.replacement_schedule_id)
  )

  return (
    <div
      className={cn(
        'flex min-h-20 flex-col items-start gap-1 rounded-md border border-border p-2 text-left transition-colors hover:bg-accent',
        // Tinting the padding days (not the current month) reads better —
        // the actual month stays at its normal, fully-readable appearance,
        // and the padding days recede by contrast instead of the current
        // month having to carry an odd background of its own.
        !inCurrentMonth && 'bg-opacity-20 bg-background',
        isToday && 'border-primary'
      )}
    >
      <button
        type="button"
        onClick={() => onCreateForDate(dateStr)}
        aria-label={
          resolved.length > 0 || cancelled.length > 0
            ? `新增 ${dateStr} 排程`
            : `${dateStr}：尚未排程`
        }
        className={cn(
          'flex size-5 select-none items-center justify-center rounded-full text-label',
          isToday ? 'bg-primary font-bold text-primary-foreground' : 'text-muted-foreground'
        )}
      >
        {day.getUTCDate()}
      </button>
      {resolved.map(schedule => (
        <MonthScheduleChip
          key={schedule.id}
          schedule={schedule}
          dateStr={dateStr}
          isReplacement={replacementIds.has(schedule.id)}
          onEditSchedule={onEditSchedule}
        />
      ))}
      {cancelled.map(schedule => (
        <button
          key={`cancelled-${schedule.id}`}
          type="button"
          onClick={() => onRestoreOccurrence(schedule, dateStr)}
          className="w-full select-none rounded bg-muted px-1.5 py-1 text-left text-label text-muted-foreground line-through"
          aria-label={`${dateStr}：已取消，點擊恢復`}
        >
          {schedule.start_time.slice(0, 5)} · 已取消
        </button>
      ))}
    </div>
  )
}

export function CalendarView({
  schedules,
  exceptions,
  timezone,
  mode,
  onEditSchedule,
  onCreateForDate,
  onRestoreOccurrence,
}: CalendarViewProps) {
  const today = todayInTimeZone(timezone)
  const [anchor, setAnchor] = useState(() => calendarDate(today))

  const weekDays = useMemo(() => {
    const start = startOfWeek(anchor)
    return Array.from({ length: 7 }, (_, i) => addDays(start, i))
  }, [anchor])

  const monthDays = useMemo(() => {
    const start = startOfMonthGrid(anchor)
    const count = monthGridWeekCount(anchor) * 7
    return Array.from({ length: count }, (_, i) => addDays(start, i))
  }, [anchor])

  const goPrev = () =>
    setAnchor(prev => (mode === 'week' ? addDays(prev, -7) : addMonths(prev, -1)))
  const goNext = () => setAnchor(prev => (mode === 'week' ? addDays(prev, 7) : addMonths(prev, 1)))
  const goToday = () => setAnchor(calendarDate(today))

  const rangeLabel =
    mode === 'week'
      ? `${weekDays[0].getUTCFullYear()}/${weekDays[0].getUTCMonth() + 1}/${weekDays[0].getUTCDate()} – ${weekDays[6].getUTCMonth() + 1}/${weekDays[6].getUTCDate()}`
      : `${anchor.getUTCFullYear()}年${anchor.getUTCMonth() + 1}月`

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={goPrev}
            aria-label={mode === 'week' ? '上一週' : '上一個月'}
          >
            <Icon icon="fa-solid fa-chevron-left" wrapperClassName="size-3" />
          </Button>
          <Button variant="outline" size="sm" onClick={goToday}>
            今天
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="size-8"
            onClick={goNext}
            aria-label={mode === 'week' ? '下一週' : '下一個月'}
          >
            <Icon icon="fa-solid fa-chevron-right" wrapperClassName="size-3" />
          </Button>
          <span className="ml-2 text-sub font-medium">{rangeLabel}</span>
        </div>
      </div>

      {mode === 'week' ? (
        <WeekTimeline
          days={weekDays}
          schedules={schedules}
          exceptions={exceptions}
          timezone={timezone}
          onEditSchedule={onEditSchedule}
          onCreateForDate={onCreateForDate}
          onRestoreOccurrence={onRestoreOccurrence}
        />
      ) : (
        <div className="grid grid-cols-7 gap-2">
          {WEEK_DISPLAY_ORDER.map(i => (
            <div key={i} className="text-center text-label text-muted-foreground">
              {WEEKDAY_LABELS[i]}
            </div>
          ))}

          {monthDays.map(day => (
            <MonthDayCell
              key={toDateStr(day)}
              day={day}
              schedules={schedules}
              exceptions={exceptions}
              timezone={timezone}
              isToday={toDateStr(day) === today}
              inCurrentMonth={day.getUTCMonth() === anchor.getUTCMonth()}
              onEditSchedule={onEditSchedule}
              onCreateForDate={onCreateForDate}
              onRestoreOccurrence={onRestoreOccurrence}
            />
          ))}
        </div>
      )}
    </div>
  )
}
