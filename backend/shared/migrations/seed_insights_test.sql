-- ============================================================
-- Insights test seed — inserts fake sessions, chatters, and events
-- Uses the first enabled channel automatically.
-- Safe to re-run (ON CONFLICT DO NOTHING on all detail tables).
-- ============================================================

DO $$
DECLARE
    ch TEXT;
    s1  INT;
    s2  INT;
    s3  INT;
BEGIN
    SELECT channel_id INTO ch FROM channels WHERE channel_name = 'llazypilot' LIMIT 1;
    IF ch IS NULL THEN
        RAISE EXCEPTION 'Channel llazypilot not found.';
    END IF;

    -- ── Sessions (one at a time to capture ids) ───────────────
    INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
    VALUES (ch,
            NOW() - INTERVAL '25 days',
            NOW() - INTERVAL '25 days' + INTERVAL '4 hours',
            'Late Night Gaming', 'Stardew Valley')
    RETURNING id INTO s1;

    INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
    VALUES (ch,
            NOW() - INTERVAL '12 days',
            NOW() - INTERVAL '12 days' + INTERVAL '5 hours 30 minutes',
            '周末放鬆直播', 'Minecraft')
    RETURNING id INTO s2;

    INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
    VALUES (ch,
            NOW() - INTERVAL '3 days',
            NOW() - INTERVAL '3 days' + INTERVAL '3 hours',
            '新遊戲初見', 'Hollow Knight')
    RETURNING id INTO s3;

    -- ── Chatter stats ─────────────────────────────────────────
    INSERT INTO chatter_stats
        (session_id, channel_id, user_id, username, display_name, message_count, last_message_at)
    VALUES
        (s1, ch, 'uid_alice', 'alice_tw',   'Alice',   312, NOW() - INTERVAL '25 days' + INTERVAL '3h 55m'),
        (s2, ch, 'uid_alice', 'alice_tw',   'Alice',   287, NOW() - INTERVAL '12 days' + INTERVAL '5h 20m'),
        (s3, ch, 'uid_alice', 'alice_tw',   'Alice',   198, NOW() - INTERVAL '3 days'  + INTERVAL '2h 50m'),

        (s1, ch, 'uid_bob',   'b0b_gamer',  'Bob',     145, NOW() - INTERVAL '25 days' + INTERVAL '3h 30m'),
        (s2, ch, 'uid_bob',   'b0b_gamer',  'Bob',     212, NOW() - INTERVAL '12 days' + INTERVAL '5h 00m'),

        (s2, ch, 'uid_carol', 'carol_chan', 'Carol',    88, NOW() - INTERVAL '12 days' + INTERVAL '4h 10m'),
        (s3, ch, 'uid_carol', 'carol_chan', 'Carol',    54, NOW() - INTERVAL '3 days'  + INTERVAL '2h 00m'),

        (s3, ch, 'uid_dave',  'dave_new',   'Dave',     23, NOW() - INTERVAL '3 days'  + INTERVAL '1h 30m'),

        (s1, ch, 'uid_elena', 'elena_vip',  'Elena',   178, NOW() - INTERVAL '25 days' + INTERVAL '3h 45m'),
        (s3, ch, 'uid_elena', 'elena_vip',  'Elena',    91, NOW() - INTERVAL '3 days'  + INTERVAL '2h 40m'),

        (s1, ch, 'uid_frank', 'frankXlurk', NULL,       12, NOW() - INTERVAL '25 days' + INTERVAL '1h 05m'),

        (s2, ch, 'uid_grace', 'graceful_g', 'Grace',    67, NOW() - INTERVAL '12 days' + INTERVAL '3h 20m'),
        (s3, ch, 'uid_grace', 'graceful_g', 'Grace',    89, NOW() - INTERVAL '3 days'  + INTERVAL '2h 55m'),

        (s2, ch, 'uid_hiro',  'hiro_jp',    'ヒロ',    256, NOW() - INTERVAL '12 days' + INTERVAL '5h 25m')
    ON CONFLICT (session_id, user_id) DO NOTHING;

    -- ── Stream events ─────────────────────────────────────────
    INSERT INTO stream_events
        (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
    VALUES
        (s3, ch, 'follow', 'uid_dave',  'dave_new',   'Dave',  NULL,
         NOW() - INTERVAL '3 days'  + INTERVAL '45m'),
        (s2, ch, 'follow', 'uid_grace', 'graceful_g', 'Grace', NULL,
         NOW() - INTERVAL '12 days' + INTERVAL '30m'),
        (s1, ch, 'follow', 'uid_frank', 'frankXlurk', NULL,    NULL,
         NOW() - INTERVAL '25 days' + INTERVAL '20m'),

        (s1, ch, 'subscribe', 'uid_elena', 'elena_vip', 'Elena',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '25 days' + INTERVAL '2h 10m'),
        (s2, ch, 'subscribe', 'uid_bob', 'b0b_gamer', 'Bob',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '1h 45m'),
        (s3, ch, 'subscribe', 'uid_alice', 'alice_tw', 'Alice',
         '{"tier":"2000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '3 days'  + INTERVAL '1h 20m'),

        (s1, ch, 'cheer', 'uid_elena', 'elena_vip', NULL,
         '{"bits":500}'::jsonb,
         NOW() - INTERVAL '25 days' + INTERVAL '3h 00m'),
        (s2, ch, 'cheer', 'uid_elena', 'elena_vip', NULL,
         '{"bits":1000}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '4h 30m'),
        (s3, ch, 'cheer', 'uid_bob', 'b0b_gamer', NULL,
         '{"bits":100}'::jsonb,
         NOW() - INTERVAL '3 days'  + INTERVAL '2h 15m'),

        (s2, ch, 'raid', 'uid_raider', 'raider_chan', NULL,
         '{"viewers":45,"from_broadcaster_id":"uid_raider","from_broadcaster_name":"raider_chan"}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '2h 00m')
    ON CONFLICT DO NOTHING;

    -- ── Command stats ─────────────────────────────────────────
    INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
    VALUES
        (s1, ch, '!lurk',    42, NOW() - INTERVAL '25 days' + INTERVAL '3h 50m'),
        (s1, ch, '!discord', 18, NOW() - INTERVAL '25 days' + INTERVAL '3h 30m'),
        (s1, ch, '!clip',    11, NOW() - INTERVAL '25 days' + INTERVAL '2h 00m'),
        (s2, ch, '!lurk',    55, NOW() - INTERVAL '12 days' + INTERVAL '5h 10m'),
        (s2, ch, '!discord', 23, NOW() - INTERVAL '12 days' + INTERVAL '4h 50m'),
        (s2, ch, '!今日',    14, NOW() - INTERVAL '12 days' + INTERVAL '3h 00m'),
        (s3, ch, '!lurk',    38, NOW() - INTERVAL '3 days'  + INTERVAL '2h 40m'),
        (s3, ch, '!clip',    19, NOW() - INTERVAL '3 days'  + INTERVAL '2h 20m'),
        (s3, ch, '!discord',  9, NOW() - INTERVAL '3 days'  + INTERVAL '1h 00m')
    ON CONFLICT (session_id, command_name) DO NOTHING;

    RAISE NOTICE 'Seed OK — channel: %  sessions: % % %', ch, s1, s2, s3;
END;
$$;
