-- Backfill viewer_attendance_streaks from historical chatter_stats.
-- Computes the current streak (consecutive sessions ending at each viewer's
-- latest attendance) using the same logic as update_attendance_streaks.
WITH
sessions_ranked AS (
    SELECT
        id,
        channel_id,
        started_at,
        ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY started_at ASC) AS session_num
    FROM stream_sessions
    WHERE ended_at IS NOT NULL
),
attendance AS (
    SELECT
        cs.channel_id,
        cs.user_id,
        cs.session_id,
        sr.session_num
    FROM chatter_stats cs
    JOIN sessions_ranked sr ON sr.id = cs.session_id AND sr.channel_id = cs.channel_id
),
-- Islands-and-gaps: consecutive attended sessions share the same streak_group value
viewer_streaks AS (
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
-- Latest session each viewer attended
viewer_latest AS (
    SELECT channel_id, user_id, MAX(session_num) AS last_session_num
    FROM attendance
    GROUP BY channel_id, user_id
),
-- Identify the streak_group that contains the viewer's latest session
latest_group AS (
    SELECT vs.channel_id, vs.user_id, vs.streak_group
    FROM viewer_streaks vs
    JOIN viewer_latest vl
        ON vl.channel_id = vs.channel_id
       AND vl.user_id    = vs.user_id
       AND vl.last_session_num = vs.session_num
),
-- Count sessions in that group = current streak length
streak_counts AS (
    SELECT vs.channel_id, vs.user_id, COUNT(*) AS streak_count
    FROM viewer_streaks vs
    JOIN latest_group lg
        ON lg.channel_id   = vs.channel_id
       AND lg.user_id      = vs.user_id
       AND lg.streak_group = vs.streak_group
    GROUP BY vs.channel_id, vs.user_id
),
-- Resolve the actual session_id for the last attended session
last_session_ids AS (
    SELECT vs.channel_id, vs.user_id, vs.session_id
    FROM viewer_streaks vs
    JOIN viewer_latest vl
        ON vl.channel_id     = vs.channel_id
       AND vl.user_id        = vs.user_id
       AND vl.last_session_num = vs.session_num
)
INSERT INTO viewer_attendance_streaks (channel_id, user_id, streak_count, last_session_id, updated_at)
SELECT sc.channel_id, sc.user_id, sc.streak_count, ls.session_id, NOW()
FROM streak_counts sc
JOIN last_session_ids ls ON ls.channel_id = sc.channel_id AND ls.user_id = sc.user_id
ON CONFLICT (channel_id, user_id) DO UPDATE SET
    streak_count    = EXCLUDED.streak_count,
    last_session_id = EXCLUDED.last_session_id,
    updated_at      = EXCLUDED.updated_at;
