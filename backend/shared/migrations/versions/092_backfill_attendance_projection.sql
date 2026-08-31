-- Historical watch_seconds were written only after a successful chatters API
-- response. They prove at least one complete non-empty observation; exact legacy
-- snapshot counts and complete empty snapshots cannot be reconstructed.
UPDATE stream_sessions AS ss
SET attendance_snapshot_count = 1
WHERE ss.attendance_snapshot_count = 0
  AND EXISTS (
      SELECT 1
      FROM chatter_stats stats
      WHERE stats.session_id = ss.id
        AND stats.channel_id = ss.channel_id
        AND stats.watch_seconds > 0
  );

-- viewer_attendance_streaks is a rebuildable projection. Recompute it across
-- eligible sessions only, and set current streak to zero when the viewer missed
-- the channel's latest eligible session.
DELETE FROM viewer_attendance_streaks;

WITH
eligible_sessions AS (
    SELECT
        id,
        channel_id,
        ROW_NUMBER() OVER (
            PARTITION BY channel_id
            ORDER BY started_at ASC, id ASC
        ) AS session_num
    FROM stream_sessions
    WHERE ended_at IS NOT NULL
      AND attendance_snapshot_count > 0
),
attendance AS (
    SELECT DISTINCT
        stats.channel_id,
        stats.user_id,
        stats.session_id,
        eligible.session_num
    FROM chatter_stats stats
    JOIN eligible_sessions eligible
      ON eligible.id = stats.session_id
     AND eligible.channel_id = stats.channel_id
),
streak_rows AS (
    SELECT
        channel_id,
        user_id,
        session_id,
        session_num,
        session_num - ROW_NUMBER() OVER (
            PARTITION BY channel_id, user_id
            ORDER BY session_num
        ) AS streak_group
    FROM attendance
),
group_counts AS (
    SELECT channel_id, user_id, streak_group, COUNT(*)::INT AS streak_count
    FROM streak_rows
    GROUP BY channel_id, user_id, streak_group
),
best_streaks AS (
    SELECT channel_id, user_id, MAX(streak_count)::INT AS best_streak
    FROM group_counts
    GROUP BY channel_id, user_id
),
latest_eligible AS (
    SELECT channel_id, MAX(session_num) AS session_num
    FROM eligible_sessions
    GROUP BY channel_id
),
current_groups AS (
    SELECT streak.channel_id, streak.user_id, streak.streak_group
    FROM streak_rows streak
    JOIN latest_eligible latest
      ON latest.channel_id = streak.channel_id
     AND latest.session_num = streak.session_num
),
current_streaks AS (
    SELECT counts.channel_id, counts.user_id, counts.streak_count
    FROM group_counts counts
    JOIN current_groups current
      ON current.channel_id = counts.channel_id
     AND current.user_id = counts.user_id
     AND current.streak_group = counts.streak_group
),
last_attendance AS (
    SELECT DISTINCT ON (channel_id, user_id)
        channel_id,
        user_id,
        session_id
    FROM streak_rows
    ORDER BY channel_id, user_id, session_num DESC
)
INSERT INTO viewer_attendance_streaks
    (channel_id, user_id, streak_count, best_streak, last_session_id, updated_at)
SELECT
    best.channel_id,
    best.user_id,
    COALESCE(current.streak_count, 0),
    best.best_streak,
    latest.session_id,
    NOW()
FROM best_streaks best
JOIN last_attendance latest
  ON latest.channel_id = best.channel_id
 AND latest.user_id = best.user_id
LEFT JOIN current_streaks current
  ON current.channel_id = best.channel_id
 AND current.user_id = best.user_id;
