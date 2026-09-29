-- Migration 143: convert legacy empty one-off skip sentinels into explicit
-- cancellations. This intentionally reproduces the old day-level suppression:
-- every recurring definition on the matching weekday is cancelled for that date.

INSERT INTO stream_schedule_occurrence_exceptions (
    channel_id,
    recurring_schedule_id,
    occurrence_date,
    kind
)
SELECT
    sentinel.channel_id,
    recurring.id,
    sentinel.specific_date,
    'cancelled'
FROM stream_schedules AS sentinel
JOIN stream_schedules AS recurring
  ON recurring.channel_id = sentinel.channel_id
 AND recurring.kind = 'recurring'
 AND recurring.weekday = EXTRACT(ISODOW FROM sentinel.specific_date)::INT - 1
WHERE sentinel.kind = 'one_off'
  AND sentinel.enabled = TRUE
  AND sentinel.title_template = ''
  AND NOT EXISTS (
      SELECT 1
      FROM stream_schedule_segments AS segment
      WHERE segment.schedule_id = sentinel.id
  )
ON CONFLICT (recurring_schedule_id, occurrence_date) DO NOTHING;

UPDATE stream_schedules AS sentinel
SET enabled = FALSE
WHERE sentinel.kind = 'one_off'
  AND sentinel.enabled = TRUE
  AND sentinel.title_template = ''
  AND NOT EXISTS (
      SELECT 1
      FROM stream_schedule_segments AS segment
      WHERE segment.schedule_id = sentinel.id
  );
