import { useEffect, useState } from 'react'

import {
  searchStreamScheduleGames,
  type StreamSchedule,
  type StreamScheduleSegment,
} from '@/api/streamSchedule'
import { Icon } from '@/components/primitives'
import { Badge } from '@/components/ui'

import { calendarDate, timeZoneOffsetLabel } from './calendar'
import { WEEKDAY_LABELS } from './constants'
import { crossesMidnight, endTimeFor } from './time'

interface NextScheduleCardProps {
  date: string
  schedule: StreamSchedule
  opening: StreamScheduleSegment | null
  timezone: string
}

const boxArtCache = new Map<string, string | null>()
const SHELL_CLASS =
  'min-h-48 overflow-hidden rounded-xl border border-border bg-muted/25 sm:min-h-0'
const BODY_CLASS = 'flex min-w-0 gap-4 p-3 sm:gap-5 sm:p-4'
const COVER_CLASS =
  'h-24 w-18 shrink-0 select-none overflow-hidden rounded-lg bg-muted sm:h-28 sm:w-21'

function categoryCoverUrl(template: string, width: number, height: number): string {
  return template.replace('{width}', String(width)).replace('{height}', String(height))
}

function useCategoryCover(
  gameId: string | null,
  gameName: string | null
): { cover: string | null; loading: boolean } {
  const [, forceRender] = useState(0)

  useEffect(() => {
    if (!gameId || !gameName || boxArtCache.has(gameId)) return

    let cancelled = false
    searchStreamScheduleGames(gameName)
      .then(matches => {
        const template = matches.find(match => match.id === gameId)?.box_art_url
        const result = template ? categoryCoverUrl(template, 96, 128) : null
        boxArtCache.set(gameId, result)
        if (!cancelled) forceRender(value => value + 1)
      })
      .catch(() => {
        boxArtCache.set(gameId, null)
        if (!cancelled) forceRender(value => value + 1)
      })

    return () => {
      cancelled = true
    }
  }, [gameId, gameName])

  const resolved = gameId ? boxArtCache.has(gameId) : true
  return {
    cover: gameId ? (boxArtCache.get(gameId) ?? null) : null,
    loading: Boolean(gameId && gameName && !resolved),
  }
}

function readableDate(date: string): string {
  const value = calendarDate(date)
  const weekday = WEEKDAY_LABELS[(value.getUTCDay() + 6) % 7]
  return `${value.getUTCFullYear()} 年 ${value.getUTCMonth() + 1} 月 ${value.getUTCDate()} 日 · ${weekday}`
}

function readableTime(schedule: StreamSchedule): string {
  const start = schedule.start_time.slice(0, 5)
  const end = endTimeFor(start, schedule.duration_minutes)
  return `${start}–${end}${crossesMidnight(start, schedule.duration_minutes) ? '（隔天）' : ''}`
}

export function NextScheduleCardSkeleton() {
  return (
    <section aria-label="載入下一場直播" aria-busy="true" className={SHELL_CLASS}>
      <div className={BODY_CLASS}>
        <div
          data-testid="next-schedule-cover-skeleton"
          className={`${COVER_CLASS} motion-safe:animate-pulse`}
        />
        <div
          aria-hidden="true"
          className="flex min-w-0 flex-1 flex-col justify-center gap-3 motion-safe:animate-pulse"
        >
          <div className="h-5 w-2/3 max-w-80 rounded bg-muted" />
          <div className="h-4 w-36 rounded bg-muted" />
          <div className="flex flex-wrap gap-3">
            <div className="h-3.5 w-48 rounded bg-muted" />
            <div className="h-3.5 w-28 rounded bg-muted" />
          </div>
        </div>
      </div>
    </section>
  )
}

export function NextScheduleCardEmpty() {
  return (
    <section aria-label="下一場直播" className={SHELL_CLASS}>
      <div className={BODY_CLASS}>
        <div
          data-testid="next-schedule-empty-cover"
          className={`${COVER_CLASS} flex items-center justify-center text-muted-foreground`}
        >
          <Icon icon="fa-solid fa-calendar" wrapperClassName="size-5" />
        </div>
        <div className="flex min-w-0 flex-1 flex-col justify-center gap-1">
          <p className="font-medium text-foreground">尚無即將到來的排程</p>
          <p className="text-sub text-muted-foreground">新增排程後，下一場直播會顯示在這裡。</p>
        </div>
      </div>
    </section>
  )
}

export function NextScheduleCard({ date, schedule, opening, timezone }: NextScheduleCardProps) {
  const title = opening?.title_template || schedule.title_template || '未設定標題'
  const gameId = opening?.game_id ?? null
  const gameName = opening?.game_name ?? null
  const { cover, loading: coverLoading } = useCategoryCover(gameId, gameName)

  return (
    <section aria-label="下一場直播" className={SHELL_CLASS}>
      <div className={BODY_CLASS}>
        <div className={COVER_CLASS}>
          {cover && gameName ? (
            <img
              src={cover}
              alt={`${gameName} 分類封面`}
              width="96"
              height="128"
              draggable={false}
              className="size-full select-none object-cover"
            />
          ) : (
            <div
              role="img"
              aria-label={
                gameName
                  ? `${gameName} 分類封面${coverLoading ? '載入中' : '無法載入'}`
                  : '未設定分類封面'
              }
              className="flex size-full items-center justify-center text-muted-foreground"
            >
              <Icon icon="fa-solid fa-gamepad" wrapperClassName="size-5" />
            </div>
          )}
        </div>

        <div className="flex min-w-0 flex-1 flex-col justify-center gap-3">
          <div className="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-1">
            <span className="shrink-0 text-sub font-medium text-primary">下一場直播</span>
            <h3 className="min-w-0 text-balance text-base font-semibold text-foreground sm:text-lg">
              {title}
            </h3>
            <Badge variant="secondary" className="shrink-0">
              {schedule.kind === 'recurring' ? '每週固定' : '單次排程'}
            </Badge>
          </div>

          <div className="flex min-w-0 items-center gap-2 text-sub text-muted-foreground">
            <Icon icon="fa-solid fa-gamepad" wrapperClassName="size-3.5 shrink-0" />
            <span className="truncate">{gameName || '未設定分類'}</span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-label text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Icon icon="fa-solid fa-calendar" wrapperClassName="size-3.5" />
              {readableDate(date)}
            </span>
            <span className="flex items-center gap-1.5 font-mono tabular-nums">
              <Icon icon="fa-solid fa-clock" wrapperClassName="size-3.5" />
              {readableTime(schedule)}
            </span>
            <span className="font-mono tabular-nums">{timeZoneOffsetLabel(timezone)}</span>
          </div>
        </div>
      </div>
    </section>
  )
}
