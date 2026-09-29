import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  cancelStreamScheduleOccurrence,
  createStreamSchedule,
  deleteStreamSchedule,
  type ScheduleKind,
  type StreamSchedule,
  type StreamScheduleOccurrenceException,
  updateStreamSchedule,
} from '@/api/streamSchedule'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Separator,
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Switch,
  Tabs,
  TabsList,
  TabsTrigger,
  Textarea,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

import {
  liveElapsedMinutesFor,
  timeZoneOffsetLabel,
  todayInTimeZone,
  weekdayInTimeZone,
} from './calendar'
import { WEEK_DISPLAY_ORDER, WEEKDAY_LABELS } from './constants'
import { GamePicker, type GameValue } from './GamePicker'
import { SegmentList } from './SegmentList'
import { crossesMidnight, durationBetween, endTimeFor } from './time'
import type { CreatePrefill, EditingState } from './types'

interface FormState {
  weekday: number
  specificDate: string
  startTime: string
  endTime: string
  titleTemplate: string
  game: GameValue | null
  enabled: boolean
  saving: boolean
}

function initialForm(kind: ScheduleKind, timezone: string, prefill?: CreatePrefill): FormState {
  return {
    weekday: prefill?.weekday ?? weekdayInTimeZone(new Date(), timezone),
    specificDate: kind === 'one_off' ? (prefill?.specificDate ?? todayInTimeZone(timezone)) : '',
    startTime: '20:00',
    endTime: '23:00',
    titleTemplate: '',
    game: null,
    enabled: true,
    saving: false,
  }
}

function toForm(schedule: StreamSchedule): FormState {
  const startTime = schedule.start_time.slice(0, 5)
  return {
    weekday: schedule.weekday ?? 0,
    specificDate: schedule.specific_date ?? '',
    startTime,
    endTime: endTimeFor(startTime, schedule.duration_minutes),
    titleTemplate: schedule.title_template,
    game: null,
    enabled: schedule.enabled,
    saving: false,
  }
}

interface ScheduleSheetProps {
  editing: EditingState | null
  timezone: string
  onSaved: (schedule: StreamSchedule) => void
  onDeleted: (id: number) => void
  onOccurrenceCancelled: (exception: StreamScheduleOccurrenceException) => void
  onClose: () => void
}

/** Outer shell owns the Sheet's open/close so its animation survives; the inner
 * form is keyed by editing target so it remounts (fresh local state, no effect
 * needed to re-sync form fields when the user opens a different schedule). */
export function ScheduleSheet({
  editing,
  timezone,
  onSaved,
  onDeleted,
  onOccurrenceCancelled,
  onClose,
}: ScheduleSheetProps) {
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  const [confirmDiscard, setConfirmDiscard] = useState(false)
  const key = editing
    ? editing.mode === 'edit'
      ? `edit-${editing.schedule.id}`
      : 'create'
    : 'closed'

  const requestClose = () => {
    if (hasUnsavedChanges) {
      setConfirmDiscard(true)
      return
    }
    onClose()
  }

  return (
    <>
      <Sheet open={!!editing} onOpenChange={open => !open && requestClose()}>
        <SheetContent className="gap-section">
          {editing && (
            <ScheduleSheetForm
              key={key}
              editing={editing}
              timezone={timezone}
              onSaved={onSaved}
              onDeleted={onDeleted}
              onOccurrenceCancelled={onOccurrenceCancelled}
              onDirtyChange={setHasUnsavedChanges}
              onClose={onClose}
            />
          )}
        </SheetContent>
      </Sheet>

      <AlertDialog open={confirmDiscard} onOpenChange={setConfirmDiscard}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>放棄未儲存的排程？</AlertDialogTitle>
            <AlertDialogDescription>目前輸入的內容不會保留。</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>繼續編輯</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={onClose}
            >
              放棄變更
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

interface ScheduleSheetFormProps {
  editing: EditingState
  timezone: string
  onSaved: (schedule: StreamSchedule) => void
  onDeleted: (id: number) => void
  onOccurrenceCancelled: (exception: StreamScheduleOccurrenceException) => void
  onDirtyChange: (dirty: boolean) => void
  onClose: () => void
}

function formMatches(left: FormState, right: FormState): boolean {
  return (
    left.weekday === right.weekday &&
    left.specificDate === right.specificDate &&
    left.startTime === right.startTime &&
    left.endTime === right.endTime &&
    left.titleTemplate === right.titleTemplate &&
    left.game?.id === right.game?.id &&
    left.game?.name === right.game?.name &&
    left.enabled === right.enabled
  )
}

function ScheduleSheetForm({
  editing,
  timezone,
  onSaved,
  onDeleted,
  onOccurrenceCancelled,
  onDirtyChange,
  onClose,
}: ScheduleSheetFormProps) {
  // A schedule's kind is fixed once created (the backend has no "convert" op),
  // but on create it's just another option in the form — no separate entry
  // point per kind, the weekday-vs-date choice below decides it. A prefill
  // (e.g. clicking an empty day in the calendar view) can pin the initial
  // kind/weekday/date without removing the toggle.
  const prefill = editing.mode === 'create' ? editing.prefill : undefined
  const [initial] = useState(() => {
    const initialKind =
      editing.mode === 'edit' ? editing.schedule.kind : (prefill?.kind ?? 'recurring')
    return {
      kind: initialKind,
      form:
        editing.mode === 'edit'
          ? toForm(editing.schedule)
          : initialForm(initialKind, timezone, prefill),
    }
  })
  const [kind, setKind] = useState<ScheduleKind>(initial.kind)
  const [form, setForm] = useState<FormState>(initial.form)
  const [gamePendingSelection, setGamePendingSelection] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  // After a fresh create, switch straight into "edit" so segments become addable
  // without the user re-opening the sheet — schedule_id doesn't exist until now.
  const [created, setCreated] = useState<StreamSchedule | null>(null)

  const schedule = editing.mode === 'edit' ? editing.schedule : created
  const hasUnsavedCreateChanges =
    editing.mode === 'create' &&
    !schedule &&
    (kind !== initial.kind || !formMatches(form, initial.form) || gamePendingSelection)

  useEffect(() => {
    onDirtyChange(hasUnsavedCreateChanges)
    return () => onDirtyChange(false)
  }, [hasUnsavedCreateChanges, onDirtyChange])

  const [skipping, setSkipping] = useState(false)
  // Only set when this sheet was opened by clicking a specific day on the
  // calendar (not the plain schedule table) — that's what a "skip just this
  // day" action needs to know which date to create the override for.
  const calendarDate = editing.mode === 'edit' ? editing.calendarDate : undefined
  // Skipping a day that's already happened doesn't mean anything.
  const calendarDateIsPast = !!calendarDate && calendarDate < todayInTimeZone(timezone)
  // A recurring schedule has no "it's over" state (next week's occurrence is
  // always still ahead), but a one-off's specific_date is a single fixed
  // occurrence — once that date has passed, the whole thing is history: not
  // just its segments, but its own time range and enabled toggle too. Locked
  // read-only rather than hidden, so it's still visible for reference (and
  // still deletable, for cleanup).
  const readOnly =
    !!schedule && schedule.kind === 'one_off' && !!schedule.specific_date
      ? schedule.specific_date < todayInTimeZone(timezone)
      : false
  const today = todayInTimeZone(timezone)
  const duration = durationBetween(form.startTime, form.endTime)
  const durationError =
    duration === 0
      ? '開始與結束時間不能相同'
      : duration < 30
        ? '排程至少 30 分鐘'
        : duration > 1380
          ? '排程最多 23 小時'
          : null
  const dateError =
    kind !== 'one_off' || schedule
      ? null
      : !form.specificDate
        ? '請選擇日期'
        : form.specificDate < today
          ? '日期不能早於今天'
          : null

  const setField = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm(prev => ({ ...prev, [field]: value }))

  // Only reset the kind-specific fields on toggle — keep whatever the user
  // already typed for time/title/game.
  const switchKind = (next: ScheduleKind) => {
    setKind(next)
    setForm(prev => ({
      ...prev,
      specificDate: next === 'one_off' ? prev.specificDate || todayInTimeZone(timezone) : '',
    }))
  }

  const handleSave = async () => {
    if (durationError || dateError || gamePendingSelection) return

    setField('saving', true)
    try {
      if (schedule) {
        const updated = await updateStreamSchedule(schedule.id, {
          start_time: `${form.startTime}:00`,
          duration_minutes: duration,
          enabled: form.enabled,
        })
        onSaved(updated)
        toast.success('排程已更新')
      } else {
        const createdSchedule = await createStreamSchedule({
          kind,
          weekday: kind === 'recurring' ? form.weekday : undefined,
          specific_date: kind === 'one_off' ? form.specificDate : undefined,
          start_time: `${form.startTime}:00`,
          duration_minutes: duration,
          title_template: form.titleTemplate.trim(),
          game_id: form.game?.id,
          game_name: form.game?.name,
        })
        onSaved(createdSchedule)
        setCreated(createdSchedule)
        toast.success('排程已建立')
      }
    } catch (e) {
      toastApiError(e, '儲存排程失敗')
    } finally {
      setField('saving', false)
    }
  }

  const handleDelete = async () => {
    if (!schedule) return
    try {
      await deleteStreamSchedule(schedule.id)
      onDeleted(schedule.id)
      toast.success('排程已刪除')
      onClose()
    } catch (e) {
      toastApiError(e, '刪除排程失敗')
    }
  }

  const handleSkipDay = async () => {
    if (!schedule || !calendarDate) return
    setSkipping(true)
    try {
      const exception = await cancelStreamScheduleOccurrence(schedule.id, calendarDate)
      onOccurrenceCancelled(exception)
      toast.success('已取消本次排程')
      onClose()
    } catch (e) {
      toastApiError(e, '跳過失敗')
    } finally {
      setSkipping(false)
    }
  }

  return (
    <>
      <SheetHeader>
        <SheetTitle>
          {schedule ? `編輯排程` : kind === 'recurring' ? '新增每週固定排程' : '新增單次排程'}
        </SheetTitle>
        <SheetDescription>
          {kind === 'recurring' ? '每週固定時間開台' : '只在你選的那天套用一次'}
        </SheetDescription>
      </SheetHeader>

      <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
        {readOnly && (
          <p className="text-label text-muted-foreground">
            這天已經過去，排程無法再編輯，僅能查看或刪除。
          </p>
        )}

        {(created || (editing.mode === 'edit' && editing.justCreated)) && (
          <p role="status" className="rounded-md bg-muted/40 px-3 py-2 text-sub">
            排程已建立，可繼續新增分段。
          </p>
        )}

        {!schedule && (
          <Tabs value={kind} onValueChange={v => switchKind(v as ScheduleKind)}>
            <TabsList className="w-full" aria-label="排程類型">
              <TabsTrigger value="recurring" className="flex-1">
                每週固定
              </TabsTrigger>
              <TabsTrigger value="one_off" className="flex-1">
                單次排程
              </TabsTrigger>
            </TabsList>
          </Tabs>
        )}

        {kind === 'recurring' ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-weekday">星期</Label>
            <Select
              value={String(form.weekday)}
              onValueChange={v => setField('weekday', Number(v))}
              disabled={!!schedule}
            >
              <SelectTrigger id="schedule-weekday" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {WEEK_DISPLAY_ORDER.map(i => (
                  <SelectItem key={i} value={String(i)}>
                    {WEEKDAY_LABELS[i]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Label htmlFor="schedule-date">日期</Label>
            <Input
              id="schedule-date"
              type="date"
              value={form.specificDate}
              onChange={e => setField('specificDate', e.target.value)}
              disabled={!!schedule}
              required
              min={!schedule ? today : undefined}
              aria-invalid={!!dateError}
              aria-describedby={dateError ? 'schedule-date-error' : undefined}
              className="w-full"
            />
            {dateError && (
              <span id="schedule-date-error" className="text-label text-destructive">
                {dateError}
              </span>
            )}
          </div>
        )}

        <div className="flex gap-card">
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="schedule-start">開始時間</Label>
            <Input
              id="schedule-start"
              type="time"
              value={form.startTime}
              onChange={e => setField('startTime', e.target.value)}
              disabled={readOnly}
              aria-invalid={!!durationError}
              aria-describedby="schedule-duration-feedback"
            />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="schedule-end">結束時間</Label>
            <Input
              id="schedule-end"
              type="time"
              value={form.endTime}
              onChange={e => setField('endTime', e.target.value)}
              disabled={readOnly}
              aria-invalid={!!durationError}
              aria-describedby="schedule-duration-feedback"
            />
          </div>
        </div>
        <div id="schedule-duration-feedback" className="flex flex-col gap-1">
          <span className="text-label text-muted-foreground">
            預估時長 {Math.floor(duration / 60)} 小時 {duration % 60} 分
            {crossesMidnight(form.startTime, duration) && '（結束於隔天）'} ·{' '}
            {timeZoneOffsetLabel(timezone)}
          </span>
          {durationError && <span className="text-label text-destructive">{durationError}</span>}
        </div>

        {!schedule && (
          <>
            <div className="flex flex-col gap-2">
              <Label htmlFor="schedule-title">開台標題（選填）</Label>
              <Textarea
                id="schedule-title"
                value={form.titleTemplate}
                onChange={e => setField('titleTemplate', e.target.value)}
                placeholder="例：週一固定台"
                maxLength={140}
                className="min-h-16 resize-y text-sub"
              />
            </div>
            <GamePicker
              id="schedule-game"
              value={form.game}
              onChange={game => setField('game', game)}
              onPendingSelectionChange={setGamePendingSelection}
            />
          </>
        )}

        {schedule && (
          <SettingRow title="啟用" description="關閉後這筆排程不會自動套用">
            <Switch
              aria-label="啟用"
              checked={form.enabled}
              onCheckedChange={v => setField('enabled', v)}
              disabled={readOnly}
            />
          </SettingRow>
        )}

        {schedule && kind === 'recurring' && calendarDate && !calendarDateIsPast && (
          <div className="flex items-center justify-between gap-2 rounded-md border border-border p-2">
            <div className="flex flex-col">
              <span className="text-sub font-medium">取消 {calendarDate}</span>
              <span className="text-label text-muted-foreground">只取消這次</span>
            </div>
            <Button variant="outline" size="sm" onClick={handleSkipDay} disabled={skipping}>
              {skipping ? <Spinner className="size-3.5" /> : '取消本次'}
            </Button>
          </div>
        )}

        {schedule && (
          <>
            <Separator />
            <div className="flex flex-col gap-2">
              <Label>分段設定</Label>
              <SegmentList
                scheduleId={schedule.id}
                startTime={schedule.start_time.slice(0, 5)}
                durationMinutes={schedule.duration_minutes}
                elapsedMinutes={liveElapsedMinutesFor(schedule, new Date(), timezone)}
                disabled={readOnly}
              />
            </div>
          </>
        )}
      </div>

      <SheetFooter className="shrink-0 flex-row gap-2">
        {schedule && (
          <Button variant="destructive" onClick={() => setConfirmDelete(true)}>
            <Icon icon="fa-solid fa-trash" wrapperClassName="mr-1.5 size-3" />
            刪除
          </Button>
        )}
        <div className="flex-1" />
        <SheetClose asChild>
          <Button variant="outline">關閉</Button>
        </SheetClose>
        <Button
          onClick={handleSave}
          disabled={
            form.saving || readOnly || !!durationError || !!dateError || gamePendingSelection
          }
        >
          {form.saving && <Spinner className="mr-1.5" />}
          {schedule ? '儲存變更' : '建立排程'}
        </Button>
      </SheetFooter>

      <DeleteConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="確定刪除這筆排程？"
        description="連同底下所有分段一起刪除，此操作無法還原。"
        onConfirm={handleDelete}
      />
    </>
  )
}
