import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
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
import { cn } from '@/lib/utils'

import { resolveActiveSegment } from './calendar'
import { GamePicker, type GameValue } from './GamePicker'
import { endTimeFor, offsetFromStart } from './time'

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

type SegmentStatus = 'past' | 'current' | 'upcoming' | 'neutral'

/** 'neutral' when the schedule isn't airing right now — every segment is
 * just "part of the plan," no current/past distinction makes sense without
 * a live "now" to compare against. */
function segmentStatus(
  segment: StreamScheduleSegment,
  activeSegment: StreamScheduleSegment | null
): SegmentStatus {
  if (!activeSegment) return 'neutral'
  if (segment.id === activeSegment.id) return 'current'
  return segment.offset_minutes < activeSegment.offset_minutes ? 'past' : 'upcoming'
}

/** Timeline node for a segment row — sits in its own grid column, outside
 * the bordered row list, so it reads as an external timeline running
 * alongside the rows rather than a decoration inside them. Placing it in
 * the same grid row as its corresponding row cell is what keeps it aligned:
 * CSS Grid stretches both to the row's tallest cell, and the two flex-1
 * spacers above/below the dot are always both present (so the dot stays
 * exactly centered on the row even at the first/last position) — only their
 * *color* is conditional, transparent where there's nothing to connect to.
 * Colored spacers meet the neighboring row's spacer exactly at the row
 * boundary, so it reads as one continuous line through every node except
 * the very first (nothing above) and very last (nothing below), whatever
 * order the rows happen to be sorted in. */
function TimelineDot({
  status,
  isFirst,
  isLast,
}: {
  status: SegmentStatus
  isFirst: boolean
  isLast: boolean
}) {
  return (
    <div className="flex flex-col items-center">
      <div className={cn('w-px flex-1', !isFirst && 'bg-border')} />
      <div
        className={cn(
          'my-1 size-2.5 shrink-0 rounded-full border-2 bg-card',
          status === 'current' && 'border-destructive bg-destructive',
          status === 'past' && 'border-border bg-border',
          (status === 'upcoming' || status === 'neutral') && 'border-primary'
        )}
      />
      <div className={cn('w-px flex-1', !isLast && 'bg-border')} />
    </div>
  )
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
  // Minutes since this schedule's own start, only when it's airing right
  // now — drives the past/current/upcoming timeline markers. Null whenever
  // it isn't currently live (not today, not enabled, or outside its time
  // window), in which case every segment just renders neutrally.
  elapsedMinutes: number | null
  // True for a one-off schedule whose specific_date has already passed —
  // the whole occurrence is history, so nothing about it (existing segments
  // or adding new ones) is editable any more.
  disabled: boolean
}

export function SegmentList({
  scheduleId,
  startTime,
  durationMinutes,
  elapsedMinutes,
  disabled,
}: SegmentListProps) {
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
  const activeSegment = useMemo(
    () => (elapsedMinutes !== null ? resolveActiveSegment(segments, elapsedMinutes) : null),
    [segments, elapsedMinutes]
  )
  // Latest segment first, "at go-live" last — a display choice, kept
  // separate from `segments` itself so nothing that computes off offsets
  // (activeSegment, availableTimeOptions) needs to care about array order.
  const sortedSegments = useMemo(
    () => [...segments].sort((a, b) => b.offset_minutes - a.offset_minutes),
    [segments]
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
      const fetched = await getStreamScheduleSegments(scheduleId)
      setSegments(fetched.sort((a, b) => a.offset_minutes - b.offset_minutes))
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
        offset_minutes: offsetFromStart(startTime, effectiveAddForm.time),
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
        offset_minutes: offsetFromStart(startTime, editForm.time),
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

  // The offset-0 segment is what applies the instant the schedule goes
  // live — removing it would leave that moment undefined, so it's
  // edit-only. Guarded here too, not just via the disabled delete button,
  // since this is a real invariant, not just a UI nicety.
  const handleDelete = async (segment: StreamScheduleSegment) => {
    if (segment.offset_minutes === 0) return
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
        時間到了自動切換標題／分類；選「開台」代表一開播就套用。沒設定分段的話，不會自動改標題或分類。
      </p>

      {disabled && (
        <p className="text-label text-muted-foreground">這天已經過去，分段無法再編輯。</p>
      )}

      {disabled ? null : addOpen ? (
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

      {loading ? (
        <Spinner className="size-4" />
      ) : (
        sortedSegments.length > 0 && (
          // A 2-column grid, not two independent flex columns — the
          // timeline dot and its row need to land in the same grid row to
          // stay aligned, which only CSS Grid's row-stretch gives for free
          // when rows vary in height (a compact display line vs. a tall
          // edit form). The bordered/divided "list" look is recreated per
          // row-cell (rounded top/bottom on the first/last, border-b on the
          // rest) since there's no single wrapping element left to put it on.
          <div className="grid grid-cols-[0.75rem_1fr] gap-x-2">
            {sortedSegments.map((segment, i) => {
              const status = segmentStatus(segment, activeSegment)
              const isPast = status === 'past' || disabled
              const isFirst = i === 0
              const isLast = i === sortedSegments.length - 1
              const cellBorder = cn(
                'border-x border-border',
                isFirst && 'rounded-t-md border-t',
                isLast ? 'rounded-b-md border-b' : 'border-b'
              )
              return editingId === segment.id ? (
                <Fragment key={segment.id}>
                  <TimelineDot status={status} isFirst={isFirst} isLast={isLast} />
                  <div className={cn(cellBorder, 'p-2')}>
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
                </Fragment>
              ) : (
                <Fragment key={segment.id}>
                  <TimelineDot status={status} isFirst={isFirst} isLast={isLast} />
                  <div
                    className={cn(
                      cellBorder,
                      'flex min-w-0 items-center justify-between gap-2 px-3 py-2',
                      isPast && 'opacity-50'
                    )}
                  >
                    <div className="flex min-w-0 flex-1 flex-col">
                      <span className="truncate text-sub font-medium">
                        {endTimeFor(startTime, segment.offset_minutes)}
                        {segment.title_template && ` · ${segment.title_template}`}
                      </span>
                      {segment.game_name && (
                        <span className="truncate text-label text-muted-foreground">
                          {segment.game_name}
                        </span>
                      )}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8"
                        onClick={() => startEdit(segment)}
                        disabled={isPast}
                      >
                        <Icon icon="fa-solid fa-pen" wrapperClassName="size-3" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="size-8 text-destructive hover:text-destructive"
                        onClick={() => handleDelete(segment)}
                        disabled={isPast || segment.offset_minutes === 0}
                      >
                        <Icon icon="fa-solid fa-trash" wrapperClassName="size-3" />
                      </Button>
                    </div>
                  </div>
                </Fragment>
              )
            })}
          </div>
        )
      )}
    </div>
  )
}
