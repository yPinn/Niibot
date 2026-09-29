import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  cancelStreamScheduleOccurrence,
  getStreamScheduleOccurrenceExceptions,
  getStreamSchedulePublishStatus,
  getStreamSchedules,
  getStreamScheduleSettings,
  replaceStreamScheduleOccurrence,
  restoreStreamScheduleOccurrence,
  retryStreamSchedulePublish,
  type StreamSchedule,
  type StreamScheduleOccurrenceException,
  type StreamSchedulePublishStatus,
  type StreamScheduleSettings,
  updateStreamSchedule,
} from '@/api/streamSchedule'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, SlideUp } from '@/components/primitives'
import { TableEmptyRow } from '@/components/TableEmptyRow'
import { TableShell } from '@/components/TableShell'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import { TwitchCapabilityAlert } from '@/components/TwitchCapabilityAlert'
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Switch,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'
import { useTwitchCapabilities } from '@/hooks/useTwitchCapabilities'
import { toastApiError } from '@/lib/toast-error'

import {
  addDays,
  calendarDate,
  firstSegment,
  minutesInTimeZone,
  resolveSchedulesForDate,
  timeStrToMinutes,
  timeZoneOffsetLabel,
  toDateStr,
  todayInTimeZone,
} from './calendar'
import { CalendarView } from './CalendarView'
import { WEEKDAY_LABELS } from './constants'
import { ScheduleSheet } from './ScheduleSheet'
import { SettingsSheet } from './SettingsSheet'
import { crossesMidnight, endTimeFor } from './time'
import { TwitchPublishStatus } from './TwitchPublishStatus'
import type { EditingState } from './types'
import { useSegmentPreview } from './useSegmentPreview'

function formatTimeRange(startTime: string, durationMinutes: number): string {
  const start = startTime.slice(0, 5)
  const end = endTimeFor(start, durationMinutes)
  const suffix = crossesMidnight(start, durationMinutes) ? '（隔天）' : ''
  return `${start}–${end}${suffix}`
}

interface ScheduleTableProps {
  schedules: StreamSchedule[]
  onToggle: (schedule: StreamSchedule) => void
  onEdit: (schedule: StreamSchedule) => void
}

function ScheduleTable({ schedules, onToggle, onEdit }: ScheduleTableProps) {
  const rows = [...schedules].sort((a, b) => {
    const aKey = a.kind === 'recurring' ? `${a.weekday}-${a.start_time}` : `${a.specific_date}`
    const bKey = b.kind === 'recurring' ? `${b.weekday}-${b.start_time}` : `${b.specific_date}`
    return aKey.localeCompare(bKey)
  })
  if (schedules.length === 0) {
    return (
      <TableShell>
        <TableBody>
          <TableEmptyRow
            colSpan={5}
            icon="fa-solid fa-calendar"
            title="尚無排程"
            description="新增第一筆排程"
          />
        </TableBody>
      </TableShell>
    )
  }
  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[20%] text-center">類型</TableHead>
          <TableHead className="w-[20%] text-center">時段</TableHead>
          <TableHead className="text-center">標題</TableHead>
          <TableHead className="w-[8%] text-center">狀態</TableHead>
          <TableHead className="w-[7%] text-right">操作</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map(schedule => (
          <TableRow key={schedule.id}>
            <TableCell className="font-medium">
              <div className="flex items-center gap-2">
                <Badge variant="secondary">{schedule.kind === 'recurring' ? '固定' : '單次'}</Badge>
                <span>
                  {schedule.kind === 'recurring'
                    ? WEEKDAY_LABELS[schedule.weekday ?? 0]
                    : schedule.specific_date}
                </span>
              </div>
            </TableCell>
            <TableCell className="font-mono text-sub">
              {formatTimeRange(schedule.start_time, schedule.duration_minutes)}
            </TableCell>
            <TableCell className="max-w-0 truncate text-sub text-muted-foreground">
              {schedule.title_template || '—'}
            </TableCell>
            <TableCell className="text-center">
              <Switch
                aria-label={`${schedule.title_template || '排程'}狀態`}
                checked={schedule.enabled}
                onCheckedChange={() => onToggle(schedule)}
              />
            </TableCell>
            <TableCell className="text-right">
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() => onEdit(schedule)}
                aria-label="編輯排程"
              >
                <Icon icon="fa-solid fa-pen" wrapperClassName="size-3.5" />
              </Button>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </TableShell>
  )
}

function NextScheduleSummary({
  schedules,
  exceptions,
  timezone,
}: {
  schedules: StreamSchedule[]
  exceptions: StreamScheduleOccurrenceException[]
  timezone: string
}) {
  const next = useMemo(() => {
    const now = new Date()
    const today = todayInTimeZone(timezone, now)
    const todayDate = calendarDate(today)
    const nowMinutes = minutesInTimeZone(now, timezone)
    for (let offset = 0; offset <= 366; offset += 1) {
      const date = toDateStr(addDays(todayDate, offset))
      const candidates = resolveSchedulesForDate(schedules, date, timezone, exceptions)
      const upcoming = candidates.find(schedule => {
        if (offset > 0) return true
        return timeStrToMinutes(schedule.start_time) >= nowMinutes
      })
      if (upcoming) return { date, schedule: upcoming }
    }
    return null
  }, [exceptions, schedules, timezone])
  const preview = useSegmentPreview(next?.schedule.id ?? null)
  useEffect(() => {
    preview.load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [next?.schedule.id])
  const opening = firstSegment(preview.segments ?? [])

  if (!next) return <CardDescription>尚無即將到來的排程</CardDescription>
  return (
    <CardDescription>
      下一場：{next.date} {next.schedule.start_time.slice(0, 5)} ·{' '}
      {opening?.title_template || next.schedule.title_template || '未設定標題'} ·{' '}
      {opening?.game_name || '未設定分類'} · {timeZoneOffsetLabel(timezone)}
    </CardDescription>
  )
}

export default function StreamSchedule() {
  useDocumentTitle('直播排程')
  const { capability } = useTwitchCapabilities()
  const scheduleCapability = capability('stream_schedule')

  const [settings, setSettings] = useState<StreamScheduleSettings | null>(null)
  const [publishStatus, setPublishStatus] = useState<StreamSchedulePublishStatus | null>(null)
  const [publishRetrying, setPublishRetrying] = useState(false)
  const [schedules, setSchedules] = useState<StreamSchedule[]>([])
  const [exceptions, setExceptions] = useState<StreamScheduleOccurrenceException[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [displayMode, setDisplayMode] = useState<'week' | 'month' | 'list'>('week')
  const [scopePrompt, setScopePrompt] = useState<{
    schedule: StreamSchedule
    date: string
  } | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [settingsData, schedulesData, exceptionData, publishData] = await Promise.all([
        getStreamScheduleSettings(),
        getStreamSchedules(),
        getStreamScheduleOccurrenceExceptions(),
        getStreamSchedulePublishStatus().catch(() => null),
      ])
      setSettings(settingsData)
      setSchedules(schedulesData)
      setExceptions(exceptionData)
      setPublishStatus(publishData)
    } catch {
      setError('無法載入排程設定')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchData()
  }, [fetchData])

  const { toggle: handleToggle } = useOptimisticToggle<StreamSchedule>({
    setState: setSchedules,
    getId: s => s.id,
    toggleFn: (s, enabled) =>
      updateStreamSchedule(s.id, { enabled }).then(() => {
        setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
      }),
    messages: { on: '排程已啟用', off: '排程已停用', error: '切換排程狀態失敗' },
  })

  const handleSaved = (schedule: StreamSchedule) => {
    setSchedules(prev => {
      const exists = prev.some(s => s.id === schedule.id)
      return exists ? prev.map(s => (s.id === schedule.id ? schedule : s)) : [...prev, schedule]
    })
    setEditing(prev =>
      prev ? { mode: 'edit', schedule, justCreated: prev.mode === 'create' } : prev
    )
    setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
  }

  const handleDeleted = (id: number) => {
    setSchedules(prev => prev.filter(s => s.id !== id))
    setExceptions(prev => prev.filter(item => item.replacement_schedule_id !== id))
    setEditing(null)
    setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
  }

  const handlePublishRetry = async () => {
    setPublishRetrying(true)
    try {
      await retryStreamSchedulePublish()
      setPublishStatus(prev =>
        prev ? { ...prev, status: 'pending', last_error_code: null, error_count: 0 } : prev
      )
    } catch (error) {
      toastApiError(error, '重新同步 Twitch 行程表失敗')
    } finally {
      setPublishRetrying(false)
    }
  }

  const upsertException = (exception: StreamScheduleOccurrenceException) => {
    setExceptions(prev => [
      ...prev.filter(
        item =>
          item.recurring_schedule_id !== exception.recurring_schedule_id ||
          item.occurrence_date !== exception.occurrence_date
      ),
      exception,
    ])
  }

  const handleOccurrenceScope = async (scope: 'occurrence' | 'series') => {
    if (!scopePrompt) return
    const target = scopePrompt
    setScopePrompt(null)
    if (scope === 'series') {
      setEditing({ mode: 'edit', schedule: target.schedule })
      return
    }
    try {
      const replacement = await replaceStreamScheduleOccurrence(target.schedule.id, target.date)
      handleSaved(replacement.schedule)
      upsertException(replacement.exception)
      setEditing({ mode: 'edit', schedule: replacement.schedule, calendarDate: target.date })
    } catch (error) {
      toastApiError(error, '建立本次調整失敗')
    }
  }

  const handleRestoreOccurrence = async (schedule: StreamSchedule, date: string) => {
    try {
      await restoreStreamScheduleOccurrence(schedule.id, date)
      setExceptions(prev =>
        prev.filter(
          item => item.recurring_schedule_id !== schedule.id || item.occurrence_date !== date
        )
      )
      setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
    } catch (error) {
      toastApiError(error, '恢復本次排程失敗')
    }
  }

  const handleCancelOccurrence = async () => {
    if (!scopePrompt) return
    const target = scopePrompt
    setScopePrompt(null)
    try {
      upsertException(await cancelStreamScheduleOccurrence(target.schedule.id, target.date))
      setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
    } catch (error) {
      toastApiError(error, '取消本次排程失敗')
    }
  }

  return (
    <PageMain>
      <PageHeader title="直播排程" description="規劃開台時間、標題與分類">
        <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
          <Icon icon="fa-solid fa-gear" wrapperClassName="mr-1.5 size-3" />
          設定
        </Button>
        <Button size="sm" onClick={() => setEditing({ mode: 'create' })}>
          <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
          新增排程
        </Button>
      </PageHeader>

      {settings && !settings.enabled && (
        <Alert>
          <AlertDescription>自動套用已關閉；排程仍可查看與編輯。</AlertDescription>
        </Alert>
      )}

      {scheduleCapability && <TwitchCapabilityAlert capabilities={[scheduleCapability]} />}

      <TwitchPublishStatus
        value={publishStatus}
        capabilityAvailable={scheduleCapability?.available ?? true}
        retrying={publishRetrying}
        onRetry={handlePublishRetry}
      />

      <SlideUp inView>
        <Card>
          <CardHeader>
            <CardTitle>行程</CardTitle>
            <NextScheduleSummary
              schedules={schedules}
              exceptions={exceptions}
              timezone={settings?.timezone ?? 'Asia/Taipei'}
            />
            <CardAction>
              <Tabs
                value={displayMode}
                onValueChange={v => setDisplayMode(v as 'week' | 'month' | 'list')}
              >
                <TabsList>
                  <TabsTrigger value="week">週</TabsTrigger>
                  <TabsTrigger value="month">月</TabsTrigger>
                  <TabsTrigger value="list">清單</TabsTrigger>
                </TabsList>
              </Tabs>
            </CardAction>
          </CardHeader>
          <CardContent>
            {loading ? (
              <TableSkeletonRows
                count={4}
                columns={['w-[12%]', 'w-[20%]', 'flex-1', 'w-[8%]', 'w-[7%]']}
              />
            ) : error ? (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            ) : displayMode !== 'list' ? (
              <CalendarView
                schedules={schedules}
                exceptions={exceptions}
                timezone={settings?.timezone ?? 'Asia/Taipei'}
                mode={displayMode}
                onEditSchedule={(schedule, dateStr) => {
                  if (schedule.kind === 'recurring') setScopePrompt({ schedule, date: dateStr })
                  else setEditing({ mode: 'edit', schedule, calendarDate: dateStr })
                }}
                onRestoreOccurrence={handleRestoreOccurrence}
                onCreateForDate={dateStr =>
                  setEditing({
                    mode: 'create',
                    prefill: { kind: 'one_off', specificDate: dateStr },
                  })
                }
              />
            ) : (
              <ScheduleTable
                schedules={schedules}
                onToggle={handleToggle}
                onEdit={s => setEditing({ mode: 'edit', schedule: s })}
              />
            )}
          </CardContent>
        </Card>
      </SlideUp>

      <ScheduleSheet
        editing={editing}
        timezone={settings?.timezone ?? 'Asia/Taipei'}
        onSaved={handleSaved}
        onDeleted={handleDeleted}
        onOccurrenceCancelled={upsertException}
        onClose={() => setEditing(null)}
      />

      <SettingsSheet
        open={settingsOpen}
        settings={settings}
        onSaved={value => {
          setSettings(value)
          setPublishStatus(prev => (prev ? { ...prev, status: 'pending' } : prev))
        }}
        onClose={() => setSettingsOpen(false)}
      />

      <AlertDialog open={!!scopePrompt} onOpenChange={open => !open && setScopePrompt(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>調整排程</AlertDialogTitle>
            <AlertDialogDescription>選擇要修改的範圍，或取消這次排程。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="sm:justify-between sm:gap-4">
            <AlertDialogCancel>關閉</AlertDialogCancel>
            <div className="flex flex-col-reverse gap-2 sm:flex-row">
              <Button variant="destructive" onClick={handleCancelOccurrence}>
                取消這次
              </Button>
              <Button variant="outline" onClick={() => handleOccurrenceScope('series')}>
                修改每週
              </Button>
              <Button onClick={() => handleOccurrenceScope('occurrence')}>只改這次</Button>
            </div>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageMain>
  )
}
