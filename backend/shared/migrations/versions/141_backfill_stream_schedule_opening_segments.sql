-- Migration 141: make the offset-0 segment the opening title source.
--
-- This is a forward-only data migration. The legacy stream_schedules.title_template
-- column remains temporarily for expand/contract compatibility, but application
-- reads and writes now use the opening segment exclusively. A later deployment may
-- remove the legacy column after all running versions no longer reference it.
--
-- Empty one-off rows without segments are intentionally untouched: older versions
-- used those as day-level skip sentinels, and migration 143 converts them to explicit
-- occurrence exceptions.

INSERT INTO stream_schedule_segments (
    channel_id,
    schedule_id,
    offset_minutes,
    title_template,
    sort_order
)
SELECT
    schedules.channel_id,
    schedules.id,
    0,
    schedules.title_template,
    0
FROM stream_schedules AS schedules
WHERE schedules.title_template <> ''
  AND NOT EXISTS (
      SELECT 1
      FROM stream_schedule_segments AS segments
      WHERE segments.schedule_id = schedules.id
        AND segments.offset_minutes = 0
  )
ON CONFLICT (schedule_id, offset_minutes) DO NOTHING;
