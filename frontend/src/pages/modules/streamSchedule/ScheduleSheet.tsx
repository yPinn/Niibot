import { useState } from 'react'
import { toast } from 'sonner'

import {
  createStreamSchedule,
  createStreamScheduleSegment,
  deleteStreamSchedule,
  type ScheduleKind,
  type StreamSchedule,
  updateStreamSchedule,
} from '@/api/streamSchedule'
import { DeleteConfirmDialog } from '@/components/DeleteConfirmDialog'
import { Icon, Spinner } from '@/components/primitives'
import { SettingRow } from '@/components/SettingRow'
import {
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

import { todayLocalDate } from './calendar'
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

function initialForm(kind: ScheduleKind, prefill?: CreatePrefill): FormState {
  return {
    weekday: prefill?.weekday ?? 0,
    specificDate: kind === 'one_off' ? (prefill?.specificDate ?? todayLocalDate()) : '',
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
  onSaved: (schedule: StreamSchedule) => void
  onDeleted: (id: number) => void
  onClose: () => void
}

/** Outer shell owns the Sheet's open/close so its animation survives; the inner
 * form is keyed by editing target so it remounts (fresh local state, no effect
 * needed to re-sync form fields when the user opens a different schedule). */
export function ScheduleSheet({ editing, onSaved, onDeleted, onClose }: ScheduleSheetProps) {
  const key = editing
    ? editing.mode === 'edit'
      ? `edit-${editing.schedule.id}`
      : 'create'
    : 'closed'

  return (
    <Sheet open={!!editing} onOpenChange={open => !open && onClose()}>
      <SheetContent className="gap-section">
        {editing && (
          <ScheduleSheetForm
            key={key}
            editing={editing}
            onSaved={onSaved}
            onDeleted={onDeleted}
            onClose={onClose}
          />
        )}
      </SheetContent>
    </Sheet>
  )
}

interface ScheduleSheetFormProps {
  editing: EditingState
  onSaved: (schedule: StreamSchedule) => void
  onDeleted: (id: number) => void
  onClose: () => void
}

function ScheduleSheetForm({ editing, onSaved, onDeleted, onClose }: ScheduleSheetFormProps) {
  // A schedule's kind is fixed once created (the backend has no "convert" op),
  // but on create it's just another option in the form — no separate entry
  // point per kind, the weekday-vs-date choice below decides it. A prefill
  // (e.g. clicking an empty day in the calendar view) can pin the initial
  // kind/weekday/date without removing the toggle.
  const prefill = editing.mode === 'create' ? editing.prefill : undefined
  const [kind, setKind] = useState<ScheduleKind>(
    editing.mode === 'edit' ? editing.schedule.kind : (prefill?.kind ?? 'recurring')
  )
  const [form, setForm] = useState<FormState>(() =>
    editing.mode === 'edit' ? toForm(editing.schedule) : initialForm(kind, prefill)
  )
  const [confirmDelete, setConfirmDelete] = useState(false)
  // After a fresh create, switch straight into "edit" so segments become addable
  // without the user re-opening the sheet — schedule_id doesn't exist until now.
  const [created, setCreated] = useState<StreamSchedule | null>(null)

  const schedule = editing.mode === 'edit' ? editing.schedule : created
  const duration = durationBetween(form.startTime, form.endTime)

  const setField = <K extends keyof FormState>(field: K, value: FormState[K]) =>
    setForm(prev => ({ ...prev, [field]: value }))

  // Only reset the kind-specific fields on toggle — keep whatever the user
  // already typed for time/title/game.
  const switchKind = (next: ScheduleKind) => {
    setKind(next)
    setForm(prev => ({
      ...prev,
      specificDate: next === 'one_off' ? prev.specificDate || todayLocalDate() : '',
    }))
  }

  const handleSave = async () => {
    if (kind === 'one_off' && !form.specificDate) {
      toast.error('請選擇日期')
      return
    }

    setField('saving', true)
    try {
      if (schedule) {
        const updated = await updateStreamSchedule(schedule.id, {
          start_time: `${form.startTime}:00`,
          duration_minutes: duration,
          title_template: form.titleTemplate.trim(),
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
        })
        onSaved(createdSchedule)
        setCreated(createdSchedule)
        // Seed the "at go-live" segment so the schedule actually does something
        // the moment it's created — without this the schedule would silently
        // apply nothing until the user separately added a segment below.
        try {
          await createStreamScheduleSegment(createdSchedule.id, {
            offset_minutes: 0,
            title_template: form.titleTemplate.trim(),
            game_id: form.game?.id,
            game_name: form.game?.name,
          })
          toast.success('排程已建立')
        } catch (segErr) {
          toastApiError(segErr, '排程已建立，但套用標題／分類失敗，請在下方「分段設定」補設定')
        }
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

  return (
    <>
      <SheetHeader>
        <SheetTitle>
          {schedule ? `編輯排程` : kind === 'recurring' ? '新增每週固定排程' : '新增單次排程'}
        </SheetTitle>
        <SheetDescription>
          {kind === 'recurring' ? '每週固定星期幾、固定時段開台' : '只在指定的某一天套用一次'}
        </SheetDescription>
      </SheetHeader>

      <div className="flex flex-1 flex-col gap-card overflow-y-auto px-page">
        {!schedule && (
          <Tabs value={kind} onValueChange={v => switchKind(v as ScheduleKind)}>
            <TabsList className="w-full">
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
            <Label>星期</Label>
            <Select
              value={String(form.weekday)}
              onValueChange={v => setField('weekday', Number(v))}
              disabled={!!schedule}
            >
              <SelectTrigger className="w-full">
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
              className="w-fit"
            />
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
            />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="schedule-end">結束時間</Label>
            <Input
              id="schedule-end"
              type="time"
              value={form.endTime}
              onChange={e => setField('endTime', e.target.value)}
            />
          </div>
        </div>
        <span className="text-label text-muted-foreground">
          預估時長 {Math.floor(duration / 60)} 小時 {duration % 60} 分
          {crossesMidnight(form.startTime, duration) && '（結束於隔天）'}
        </span>

        {!schedule && (
          <>
            <div className="flex flex-col gap-2">
              <Label htmlFor="schedule-title">開台標題</Label>
              <Textarea
                id="schedule-title"
                value={form.titleTemplate}
                onChange={e => setField('titleTemplate', e.target.value)}
                placeholder="例：週一固定台"
                className="min-h-16 resize-y text-sub"
              />
            </div>
            <GamePicker
              id="schedule-game"
              value={form.game}
              onChange={game => setField('game', game)}
            />
          </>
        )}

        {schedule && (
          <SettingRow title="啟用" description="關閉後這筆排程不會自動套用">
            <Switch
              aria-label="啟用"
              checked={form.enabled}
              onCheckedChange={v => setField('enabled', v)}
            />
          </SettingRow>
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
        <Button onClick={handleSave} disabled={form.saving}>
          {form.saving && <Spinner className="mr-1.5" />}
          {schedule ? '儲存' : '建立'}
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
