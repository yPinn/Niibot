import type { StreamSchedule, StreamScheduleSegment } from '@/api/streamSchedule'

import { endTimeFor } from './time'

interface SchedulePreviewProps {
  schedule: StreamSchedule
  segments: StreamScheduleSegment[] | null
  loading: boolean
}

/** Shared hover-tooltip content for a schedule block, used by both the week
 * timeline and the month grid so hovering any schedule anywhere on the
 * calendar shows the same detail. */
export function SchedulePreview({ schedule, segments, loading }: SchedulePreviewProps) {
  const start = schedule.start_time.slice(0, 5)
  return (
    <div className="flex flex-col gap-1">
      <div className="font-medium">{schedule.title_template || '（未設定標題）'}</div>
      <div className="text-muted-foreground">
        {start}–{endTimeFor(start, schedule.duration_minutes)}
      </div>
      {loading ? (
        <div className="text-muted-foreground">載入分段中…</div>
      ) : segments && segments.length > 0 ? (
        <div className="flex flex-col gap-0.5 border-t border-border pt-1">
          {/* Earliest first here regardless of how the segment editor sorts
              its own list — a hover preview reads more naturally as a
              schedule of events in the order they happen. */}
          {[...segments]
            .sort((a, b) => a.offset_minutes - b.offset_minutes)
            .map(seg => (
              <div key={seg.id} className="text-muted-foreground">
                {endTimeFor(start, seg.offset_minutes)} {seg.game_name || '（未設定分類）'}
              </div>
            ))}
        </div>
      ) : null}
    </div>
  )
}
