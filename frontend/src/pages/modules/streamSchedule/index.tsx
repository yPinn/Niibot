import { useCallback, useEffect, useState } from 'react'

import {
  getStreamSchedules,
  getStreamScheduleSettings,
  type StreamSchedule,
  type StreamScheduleSettings,
  updateStreamSchedule,
} from '@/api/streamSchedule'
import { PageHeader } from '@/components/layout/PageHeader'
import { PageMain } from '@/components/layout/PageMain'
import { Icon, SlideUp } from '@/components/primitives'
import { TableEmptyRow } from '@/components/TableEmptyRow'
import { TableShell } from '@/components/TableShell'
import { TableSkeletonRows } from '@/components/TableSkeletonRows'
import {
  Alert,
  AlertDescription,
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
  TabsContent,
  TabsList,
  TabsTrigger,
} from '@/components/ui'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useOptimisticToggle } from '@/hooks/useOptimisticToggle'

import { CalendarView } from './CalendarView'
import { WEEKDAY_LABELS } from './constants'
import { ScheduleSheet } from './ScheduleSheet'
import { SettingsSheet } from './SettingsSheet'
import { crossesMidnight, endTimeFor } from './time'
import type { EditingState } from './types'

function formatTimeRange(startTime: string, durationMinutes: number): string {
  const start = startTime.slice(0, 5)
  const end = endTimeFor(start, durationMinutes)
  const suffix = crossesMidnight(start, durationMinutes) ? '（隔天）' : ''
  return `${start}–${end}${suffix}`
}

interface ScheduleTableProps {
  kind: 'recurring' | 'one_off'
  schedules: StreamSchedule[]
  onToggle: (schedule: StreamSchedule) => void
  onEdit: (schedule: StreamSchedule) => void
}

function ScheduleTable({ kind, schedules, onToggle, onEdit }: ScheduleTableProps) {
  const rows = schedules.filter(s => s.kind === kind)
  if (rows.length === 0) {
    return (
      <TableShell>
        <TableBody>
          <TableEmptyRow
            colSpan={5}
            icon="fa-solid fa-calendar"
            title={kind === 'recurring' ? '尚無每週固定排程' : '尚無單次排程'}
            description="點擊「新增排程」開始設定"
          />
        </TableBody>
      </TableShell>
    )
  }
  return (
    <TableShell>
      <TableHeader>
        <TableRow>
          <TableHead className="w-[12%] text-center">
            {kind === 'recurring' ? '星期' : '日期'}
          </TableHead>
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
              {kind === 'recurring'
                ? WEEKDAY_LABELS[schedule.weekday ?? 0]
                : schedule.specific_date}
            </TableCell>
            <TableCell className="font-mono text-sub">
              {formatTimeRange(schedule.start_time, schedule.duration_minutes)}
            </TableCell>
            <TableCell className="max-w-0 truncate text-sub text-muted-foreground">
              {schedule.title_template || '—'}
            </TableCell>
            <TableCell className="text-center">
              <Switch checked={schedule.enabled} onCheckedChange={() => onToggle(schedule)} />
            </TableCell>
            <TableCell className="text-right">
              <Button
                variant="ghost"
                size="icon"
                className="size-8"
                onClick={() => onEdit(schedule)}
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

export default function StreamSchedule() {
  useDocumentTitle('Stream Schedule')

  const [settings, setSettings] = useState<StreamScheduleSettings | null>(null)
  const [schedules, setSchedules] = useState<StreamSchedule[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState<EditingState | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [displayMode, setDisplayMode] = useState<'list' | 'calendar'>('list')

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [settingsData, schedulesData] = await Promise.all([
        getStreamScheduleSettings(),
        getStreamSchedules(),
      ])
      setSettings(settingsData)
      setSchedules(schedulesData)
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
    toggleFn: (s, enabled) => updateStreamSchedule(s.id, { enabled }).then(() => {}),
    messages: { on: '排程已啟用', off: '排程已停用', error: '切換排程狀態失敗' },
  })

  const handleSaved = (schedule: StreamSchedule) => {
    setSchedules(prev => {
      const exists = prev.some(s => s.id === schedule.id)
      return exists ? prev.map(s => (s.id === schedule.id ? schedule : s)) : [...prev, schedule]
    })
    setEditing(prev => (prev ? { mode: 'edit', schedule } : prev))
  }

  const handleDeleted = (id: number) => {
    setSchedules(prev => prev.filter(s => s.id !== id))
    setEditing(null)
  }

  return (
    <PageMain>
      <PageHeader
        title="Stream Schedule"
        description="設定固定行程的標題與遊戲分類，開台時自動套用"
      >
        <Button variant="outline" size="sm" onClick={() => setSettingsOpen(true)}>
          <Icon icon="fa-solid fa-gear" wrapperClassName="mr-1.5 size-3" />
          排程設定
        </Button>
      </PageHeader>

      {settings && !settings.enabled && (
        <Alert>
          <AlertDescription>
            「自動套用排程」目前已關閉，開台不會自動改標題或分類，可以到「排程設定」重新開啟。
          </AlertDescription>
        </Alert>
      )}

      <SlideUp inView>
        <Card>
          <CardHeader>
            <CardTitle>排程列表</CardTitle>
            <CardDescription>
              可以設定「每週固定」或「單次」的排程；同一天兩種都有的話，單次排程優先
            </CardDescription>
            <CardAction className="flex items-center gap-2">
              <Tabs
                value={displayMode}
                onValueChange={v => setDisplayMode(v as 'list' | 'calendar')}
              >
                <TabsList>
                  <TabsTrigger value="list">列表</TabsTrigger>
                  <TabsTrigger value="calendar">日曆</TabsTrigger>
                </TabsList>
              </Tabs>
              <Button size="sm" onClick={() => setEditing({ mode: 'create' })}>
                <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
                新增排程
              </Button>
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
            ) : displayMode === 'calendar' ? (
              <CalendarView
                schedules={schedules}
                onEditSchedule={(s, dateStr) =>
                  setEditing({ mode: 'edit', schedule: s, calendarDate: dateStr })
                }
                onCreateForDate={dateStr =>
                  setEditing({
                    mode: 'create',
                    prefill: { kind: 'one_off', specificDate: dateStr },
                  })
                }
              />
            ) : (
              <Tabs defaultValue="recurring">
                <TabsList>
                  <TabsTrigger value="recurring">
                    每週固定
                    <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                      {schedules.filter(s => s.kind === 'recurring').length}
                    </Badge>
                  </TabsTrigger>
                  <TabsTrigger value="one_off">
                    單次排程
                    <Badge variant="secondary" className="ml-1.5 px-1.5 text-label">
                      {schedules.filter(s => s.kind === 'one_off').length}
                    </Badge>
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="recurring">
                  <ScheduleTable
                    kind="recurring"
                    schedules={schedules}
                    onToggle={handleToggle}
                    onEdit={s => setEditing({ mode: 'edit', schedule: s })}
                  />
                </TabsContent>

                <TabsContent value="one_off">
                  <ScheduleTable
                    kind="one_off"
                    schedules={schedules}
                    onToggle={handleToggle}
                    onEdit={s => setEditing({ mode: 'edit', schedule: s })}
                  />
                </TabsContent>
              </Tabs>
            )}
          </CardContent>
        </Card>
      </SlideUp>

      <ScheduleSheet
        editing={editing}
        onSaved={handleSaved}
        onDeleted={handleDeleted}
        onClose={() => setEditing(null)}
      />

      <SettingsSheet
        open={settingsOpen}
        settings={settings}
        onSaved={setSettings}
        onClose={() => setSettingsOpen(false)}
      />
    </PageMain>
  )
}
