import { useCallback, useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  createStreamScheduleSegment,
  deleteStreamScheduleSegment,
  getStreamScheduleSegments,
  type StreamScheduleSegment,
  updateStreamScheduleSegment,
} from '@/api/streamSchedule'
import { Icon, Spinner } from '@/components/primitives'
import {
  Button,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from '@/components/ui'
import { toastApiError } from '@/lib/toast-error'

import { GamePicker, type GameValue } from './GamePicker'
import { durationBetween, endTimeFor } from './time'

const STEP_MINUTES = 30

interface RowFormState {
  time: string // HH:MM clock time, always one of timeSlotOptions() for the schedule
  title_template: string
  game: GameValue | null
}

function emptyRow(startTime: string): RowFormState {
  return { time: startTime, title_template: '', game: null }
}

function toRowForm(segment: StreamScheduleSegment, startTime: string): RowFormState {
  return {
    time: endTimeFor(startTime, segment.offset_minutes),
    title_template: segment.title_template,
    game:
      segment.game_id && segment.game_name
        ? { id: segment.game_id, name: segment.game_name }
        : null,
  }
}

/** A new segment usually tweaks just one thing (often only the category) off
 * the segment before it, so default the add-form to whatever the latest
 * (highest-offset) segment already has instead of making the user re-type a
 * title that isn't actually changing — they can still override either field. */
function inheritedRow(segments: StreamScheduleSegment[], time: string): RowFormState {
  const last = segments.at(-1)
  return {
    time,
    title_template: last?.title_template ?? '',
    game: last?.game_id && last?.game_name ? { id: last.game_id, name: last.game_name } : null,
  }
}

/** Half-hour marks across the schedule's own start–end window, as actual
 * clock times rather than a raw "minutes since start" number — picking "幾
 * 點" is a lot more direct than doing the offset math in your head. Wraps
 * past midnight the same way the schedule's own time range does. */
function timeSlotOptions(
  startTime: string,
  durationMinutes: number
): { value: string; label: string }[] {
  const options: { value: string; label: string }[] = []
  for (let offset = 0; offset <= durationMinutes; offset += STEP_MINUTES) {
    const time = endTimeFor(startTime, offset)
    options.push({ value: time, label: offset === 0 ? `${time}（開台）` : time })
  }
  return options
}

/** Only one segment can ever be "active" at a given moment, so two segments
 * sharing a time slot would just make one unreachable — excludes times
 * already claimed by other segments (`excludeSegmentId` lets the segment
 * currently being edited keep its own slot). Falls back to the full list in
 * the unlikely case every slot is already taken, rather than a dead-end
 * empty dropdown. */
function availableTimeOptions(
  allOptions: { value: string; label: string }[],
  segments: StreamScheduleSegment[],
  startTime: string,
  excludeSegmentId: number | null
): { value: string; label: string }[] {
  const used = new Set(
    segments
      .filter(s => s.id !== excludeSegmentId)
      .map(s => endTimeFor(startTime, s.offset_minutes))
  )
  const available = allOptions.filter(o => !used.has(o.value))
  return available.length > 0 ? available : allOptions
}

function firstAvailableTime(
  allOptions: { value: string; label: string }[],
  segments: StreamScheduleSegment[],
  startTime: string
): string {
  return availableTimeOptions(allOptions, segments, startTime, null)[0]?.value ?? startTime
}

interface SegmentRowProps {
  form: RowFormState
  timeOptions: { value: string; label: string }[]
  onChange: (form: RowFormState) => void
  onSubmit: () => void
  onCancel?: () => void
  submitLabel: string
  saving: boolean
}

function SegmentRow({
  form,
  timeOptions,
  onChange,
  onSubmit,
  onCancel,
  submitLabel,
  saving,
}: SegmentRowProps) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <Label className="text-label text-muted-foreground">套用時間</Label>
        <Select value={form.time} onValueChange={time => onChange({ ...form, time })}>
          <SelectTrigger className="h-8 w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {timeOptions.map(option => (
              <SelectItem key={option.value} value={option.value}>
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-col gap-1">
        <Label className="text-label text-muted-foreground">標題</Label>
        <Textarea
          value={form.title_template}
          onChange={e => onChange({ ...form, title_template: e.target.value })}
          placeholder="開台標題"
          className="min-h-12 resize-y text-sub"
        />
      </div>
      <GamePicker
        label="遊戲分類"
        labelClassName="text-label text-muted-foreground"
        inputClassName="h-8"
        value={form.game}
        onChange={game => onChange({ ...form, game })}
      />
      <div className="flex justify-end gap-1">
        {onCancel && (
          <Button variant="ghost" size="icon" className="size-8" onClick={onCancel}>
            <Icon icon="fa-solid fa-xmark" wrapperClassName="size-3.5" />
          </Button>
        )}
        <Button size="sm" className="h-8" onClick={onSubmit} disabled={saving}>
          {saving ? <Spinner className="size-3.5" /> : submitLabel}
        </Button>
      </div>
    </div>
  )
}

interface SegmentListProps {
  scheduleId: number
  startTime: string // HH:MM
  durationMinutes: number
}

export function SegmentList({ scheduleId, startTime, durationMinutes }: SegmentListProps) {
  const [segments, setSegments] = useState<StreamScheduleSegment[]>([])
  const [loading, setLoading] = useState(true)
  const [addOpen, setAddOpen] = useState(false)
  const [addForm, setAddForm] = useState<RowFormState>(() => emptyRow(startTime))
  const [adding, setAdding] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editForm, setEditForm] = useState<RowFormState>(() => emptyRow(startTime))
  const [savingId, setSavingId] = useState<number | null>(null)

  const timeOptions = useMemo(
    () => timeSlotOptions(startTime, durationMinutes),
    [startTime, durationMinutes]
  )
  const addTimeOptions = useMemo(
    () => availableTimeOptions(timeOptions, segments, startTime, null),
    [timeOptions, segments, startTime]
  )
  const editTimeOptions = useMemo(
    () => availableTimeOptions(timeOptions, segments, startTime, editingId),
    [timeOptions, segments, startTime, editingId]
  )
  // addForm.time is set once (before segments have loaded) and only changes
  // again when the user picks a new value — if segments load in and it turns
  // out to collide with one that already exists (common: schedules get one
  // auto-created at offset 0), derive the corrected value here instead of an
  // effect syncing it back into state.
  const effectiveAddForm: RowFormState = {
    ...addForm,
    time: addTimeOptions.some(o => o.value === addForm.time)
      ? addForm.time
      : (addTimeOptions[0]?.value ?? addForm.time),
  }

  const fetchSegments = useCallback(async () => {
    try {
      setSegments(await getStreamScheduleSegments(scheduleId))
    } catch (e) {
      toastApiError(e, '載入分段失敗')
    } finally {
      setLoading(false)
    }
  }, [scheduleId])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchSegments()
  }, [fetchSegments])

  const openAdd = () => {
    setAddForm(inheritedRow(segments, firstAvailableTime(timeOptions, segments, startTime)))
    setAddOpen(true)
  }

  const handleAdd = async () => {
    setAdding(true)
    try {
      const created = await createStreamScheduleSegment(scheduleId, {
        offset_minutes: durationBetween(startTime, effectiveAddForm.time),
        title_template: effectiveAddForm.title_template.trim(),
        game_id: effectiveAddForm.game?.id,
        game_name: effectiveAddForm.game?.name,
        sort_order: segments.length,
      })
      setSegments(prev => [...prev, created].sort((a, b) => a.offset_minutes - b.offset_minutes))
      setAddOpen(false)
      toast.success('已新增分段')
    } catch (e) {
      toastApiError(e, '新增分段失敗')
    } finally {
      setAdding(false)
    }
  }

  const startEdit = (segment: StreamScheduleSegment) => {
    setEditingId(segment.id)
    setEditForm(toRowForm(segment, startTime))
  }

  const handleSaveEdit = async (segment: StreamScheduleSegment) => {
    setSavingId(segment.id)
    try {
      const updated = await updateStreamScheduleSegment(segment.id, {
        offset_minutes: durationBetween(startTime, editForm.time),
        title_template: editForm.title_template.trim(),
        game_id: editForm.game?.id ?? '',
        game_name: editForm.game?.name ?? '',
      })
      setSegments(prev =>
        prev
          .map(s => (s.id === updated.id ? updated : s))
          .sort((a, b) => a.offset_minutes - b.offset_minutes)
      )
      setEditingId(null)
      toast.success('已更新分段')
    } catch (e) {
      toastApiError(e, '更新分段失敗')
    } finally {
      setSavingId(null)
    }
  }

  const handleDelete = async (segment: StreamScheduleSegment) => {
    try {
      await deleteStreamScheduleSegment(segment.id)
      setSegments(prev => prev.filter(s => s.id !== segment.id))
      toast.success('已刪除分段')
    } catch (e) {
      toastApiError(e, '刪除分段失敗')
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-label text-muted-foreground">
        依時間自動切換每個分段的標題／分類；選「開台」代表一開台就套用。未設定分段時，排程只會被記錄，不會自動變更標題或分類。
      </p>

      {loading ? (
        <Spinner className="size-4" />
      ) : (
        segments.length > 0 && (
          <div className="flex flex-col divide-y divide-border rounded-md border border-border">
            {segments.map(segment =>
              editingId === segment.id ? (
                <div key={segment.id} className="p-2">
                  <SegmentRow
                    form={editForm}
                    timeOptions={editTimeOptions}
                    onChange={setEditForm}
                    onSubmit={() => handleSaveEdit(segment)}
                    onCancel={() => setEditingId(null)}
                    submitLabel="儲存"
                    saving={savingId === segment.id}
                  />
                </div>
              ) : (
                <div key={segment.id} className="flex items-center justify-between gap-2 px-3 py-2">
                  <div className="flex min-w-0 flex-col">
                    <span className="text-sub font-medium">
                      {endTimeFor(startTime, segment.offset_minutes)}
                      {segment.offset_minutes === 0 && '（開台）'}
                      {segment.title_template && ` · ${segment.title_template}`}
                    </span>
                    {segment.game_name && (
                      <span className="text-label text-muted-foreground">{segment.game_name}</span>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => startEdit(segment)}
                    >
                      <Icon icon="fa-solid fa-pen" wrapperClassName="size-3" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(segment)}
                    >
                      <Icon icon="fa-solid fa-trash" wrapperClassName="size-3" />
                    </Button>
                  </div>
                </div>
              )
            )}
          </div>
        )
      )}

      {addOpen ? (
        <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/20 p-2">
          <SegmentRow
            form={effectiveAddForm}
            timeOptions={addTimeOptions}
            onChange={setAddForm}
            onSubmit={handleAdd}
            onCancel={() => setAddOpen(false)}
            submitLabel="新增"
            saving={adding}
          />
        </div>
      ) : (
        <Button variant="outline" size="sm" className="w-full" onClick={openAdd}>
          <Icon icon="fa-solid fa-plus" wrapperClassName="mr-1.5 size-3" />
          新增分段
        </Button>
      )}
    </div>
  )
}
