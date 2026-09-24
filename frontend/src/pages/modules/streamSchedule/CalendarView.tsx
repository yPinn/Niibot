import { useMemo, useState } from 'react'

import type { StreamSchedule } from '@/api/streamSchedule'
import { Icon } from '@/components/primitives'
import { Button, Tabs, TabsList, TabsTrigger } from '@/components/ui'
import { cn } from '@/lib/utils'

import {
  addDays,
  monthGridWeekCount,
  resolveScheduleForDate,
  startOfMonthGrid,
  startOfWeek,
  toDateStr,
  todayLocalDate,
} from './calendar'
import { WEEK_DISPLAY_ORDER, WEEKDAY_LABELS } from './constants'
import { WeekTimeline } from './WeekTimeline'

type ViewMode = 'week' | 'month'

interface CalendarViewProps {
  schedules: StreamSchedule[]
  onEditSchedule: (schedule: StreamSchedule) => void
  onCreateForDate: (dateStr: string) => void
}

function addMonths(date: Date, delta: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1)
}

export function CalendarView({ schedules, onEditSchedule, onCreateForDate }: CalendarViewProps) {
  // Week-first, matching Twitch's own schedule page — month is the
  // birds-eye view for scanning a whole month at a glance.
  const [mode, setMode] = useState<ViewMode>('week')
  const [anchor, setAnchor] = useState(() => new Date())
  const today = todayLocalDate()

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
  const goToday = () => setAnchor(new Date())

  const rangeLabel =
    mode === 'week'
      ? `${weekDays[0].getFullYear()}/${weekDays[0].getMonth() + 1}/${weekDays[0].getDate()} – ${weekDays[6].getMonth() + 1}/${weekDays[6].getDate()}`
      : `${anchor.getFullYear()}年${anchor.getMonth() + 1}月`

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
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
        <Tabs value={mode} onValueChange={v => setMode(v as ViewMode)}>
          <TabsList>
            <TabsTrigger value="week">週</TabsTrigger>
            <TabsTrigger value="month">月</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {mode === 'week' ? (
        <WeekTimeline
          days={weekDays}
          schedules={schedules}
          onEditSchedule={onEditSchedule}
          onCreateForDate={onCreateForDate}
        />
      ) : (
        <div className="grid grid-cols-7 gap-2">
          {WEEK_DISPLAY_ORDER.map(i => (
            <div key={i} className="text-center text-label text-muted-foreground">
              {WEEKDAY_LABELS[i]}
            </div>
          ))}

          {monthDays.map(day => {
            const dateStr = toDateStr(day)
            const resolved = resolveScheduleForDate(schedules, dateStr)
            const isToday = dateStr === today
            const inCurrentMonth = day.getMonth() === anchor.getMonth()

            return (
              <button
                key={dateStr}
                type="button"
                onClick={() => (resolved ? onEditSchedule(resolved) : onCreateForDate(dateStr))}
                aria-label={
                  resolved
                    ? `${dateStr}：${resolved.start_time.slice(0, 5)} ${resolved.title_template || '（已排程）'}`
                    : `${dateStr}：尚未排程`
                }
                className={cn(
                  'flex min-h-20 flex-col items-start gap-1 rounded-md border border-border p-2 text-left transition-colors hover:bg-accent',
                  !inCurrentMonth && 'opacity-40',
                  isToday && 'border-primary'
                )}
              >
                <span
                  className={cn(
                    'flex size-5 items-center justify-center rounded-full text-label',
                    isToday
                      ? 'bg-primary font-bold text-primary-foreground'
                      : 'text-muted-foreground'
                  )}
                >
                  {day.getDate()}
                </span>
                {/* Twitch-style event chip: a solid colour block per entry (one-off
                    vs. recurring get distinct colours). */}
                {resolved && (
                  <div
                    className={cn(
                      'w-full min-w-0 rounded px-1.5 py-1 text-label leading-tight',
                      resolved.kind === 'one_off'
                        ? 'bg-primary/15 text-primary'
                        : 'bg-secondary text-secondary-foreground'
                    )}
                  >
                    <div className="font-medium">{resolved.start_time.slice(0, 5)}</div>
                    {resolved.title_template && (
                      <div className="truncate text-muted-foreground">
                        {resolved.title_template}
                      </div>
                    )}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
