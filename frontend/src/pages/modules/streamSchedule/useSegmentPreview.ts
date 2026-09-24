import { useState } from 'react'

import { getStreamScheduleSegments, type StreamScheduleSegment } from '@/api/streamSchedule'

/** Segment breakdown (title/category per offset) isn't loaded with the
 * schedule list the calendar already has, so each visible block fetches its
 * own — bounded by however many distinct schedules are actually visible
 * (week: at most 7; month: at most 42 cells, but usually far fewer distinct
 * schedules once a recurring one repeats across cells), cheap enough to do
 * eagerly since a block always displays its category, not just on hover.
 * No cross-fetch cache: segments can be edited from the same sheet this
 * calendar opens, so refetching per mount (rather than risking a stale
 * cache) is the simpler correct choice. */
export function useSegmentPreview(scheduleId: number | null) {
  const [state, setState] = useState<{ id: number; segments: StreamScheduleSegment[] } | null>(null)
  const [loading, setLoading] = useState(false)

  const load = () => {
    if (scheduleId === null || loading || state?.id === scheduleId) return
    setLoading(true)
    getStreamScheduleSegments(scheduleId)
      .then(data => setState({ id: scheduleId, segments: data }))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  return { segments: state?.id === scheduleId ? state.segments : null, loading, load }
}
