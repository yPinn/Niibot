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
    s4  INT;
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

    INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
    VALUES (ch,
            NOW() - INTERVAL '1 day',
            NOW() - INTERVAL '1 day' + INTERVAL '6 hours',
            '週年慶特別直播', 'Just Chatting')
    RETURNING id INTO s4;

    -- ── Chatter stats ─────────────────────────────────────────
    -- Real Twitch accounts used for richer profile data in ViewerSheet:
    --   36128773   ola0323      affiliate + offline banner  (most active, tier-2 sub)
    --   117691767  rexyz2z      viewer    + offline banner  (tier-1 sub, bits)
    --   65359374   luming1228   viewer                      (regular chatter)
    --   1075248331 capoo_xiang  viewer    (2024 new account, matches new-follower scenario)
    --   109156102  san_mou      partner   + offline banner  (VIP, heavy bits)
    --   21018499   iceice12     viewer    (2011 account, lurker)
    --   35760596   m950101      affiliate + offline banner  (follower + chatter)
    --   193691668  after_moon   viewer                      (高活躍聊天)
    -- ── API-dependent fields (mod/vip/ban/sub status come from Twitch API, not DB) ──
    -- Replace placeholder IDs below with real channel member IDs to see those status rows:
    --   797358387  hsuyi1222   → 頻道管理員 (is_mod = true via API)
    --   794077634  kariouo     → VIP        (is_vip = true via API)
    --   REPLACE_WITH_BAN_USER_ID  → 封禁用戶    (is_banned = true via API)
    -- watch_seconds: bot polls every 300s; session lengths: s1=4h, s2=5.5h, s3=3h, s4=6h
    INSERT INTO chatter_stats
        (session_id, channel_id, user_id, username, display_name, message_count, last_message_at, watch_seconds)
    VALUES
        -- ola0323: 高活躍，幾乎全程在線
        (s1, ch, '36128773',   'ola0323',     '歐拉今天不是很想練習', 312, NOW() - INTERVAL '25 days' + INTERVAL '3h 55m', 13500),
        (s2, ch, '36128773',   'ola0323',     '歐拉今天不是很想練習', 287, NOW() - INTERVAL '12 days' + INTERVAL '5h 20m', 18600),
        (s3, ch, '36128773',   'ola0323',     '歐拉今天不是很想練習', 198, NOW() - INTERVAL '3 days'  + INTERVAL '2h 50m',  9900),

        -- rexyz2z: 中等活躍
        (s1, ch, '117691767',  'rexyz2z',     'rexyz2z',             145, NOW() - INTERVAL '25 days' + INTERVAL '3h 30m', 10800),
        (s2, ch, '117691767',  'rexyz2z',     'rexyz2z',             212, NOW() - INTERVAL '12 days' + INTERVAL '5h 00m', 15300),

        -- luming1228: 普通觀眾
        (s2, ch, '65359374',   'luming1228',  '嚕嚕閔',               88, NOW() - INTERVAL '12 days' + INTERVAL '4h 10m',  9600),
        (s3, ch, '65359374',   'luming1228',  '嚕嚕閔',               54, NOW() - INTERVAL '3 days'  + INTERVAL '2h 00m',  6600),

        -- capoo_xiang: 新觀眾，中途加入
        (s3, ch, '1075248331', 'capoo_xiang', '_咖波波_',             23, NOW() - INTERVAL '3 days'  + INTERVAL '1h 30m',  3600),

        -- san_mou: 合作夥伴，高度參與
        (s1, ch, '109156102',  'san_mou',     '三毛毛毛',            178, NOW() - INTERVAL '25 days' + INTERVAL '3h 45m', 12300),
        (s3, ch, '109156102',  'san_mou',     '三毛毛毛',             91, NOW() - INTERVAL '3 days'  + INTERVAL '2h 40m',  8700),

        -- iceice12: 潛水者，時長遠超留言數
        (s1, ch, '21018499',   'iceice12',    '古月謠',               12, NOW() - INTERVAL '25 days' + INTERVAL '1h 05m', 11400),

        -- m950101
        (s2, ch, '35760596',   'm950101',     'M950101',              67, NOW() - INTERVAL '12 days' + INTERVAL '3h 20m',  8700),
        (s3, ch, '35760596',   'm950101',     'M950101',              89, NOW() - INTERVAL '3 days'  + INTERVAL '2h 55m',  9300),

        -- after_moon: 幾乎全場在線
        (s2, ch, '193691668',  'after_moon',  '午後的月亮',          256, NOW() - INTERVAL '12 days' + INTERVAL '5h 25m', 19200),

        -- hsuyi1222（想睡覺_）— 頻道管理員，全程在線
        (s1, ch, '797358387', 'hsuyi1222', '想睡覺_',   203, NOW() - INTERVAL '25 days' + INTERVAL '3h 30m', 13800),
        (s4, ch, '797358387', 'hsuyi1222', '想睡覺_',    89, NOW() - INTERVAL '1 day'   + INTERVAL '5h 30m', 20400),

        -- kariouo — VIP
        (s3, ch, '794077634', 'kariouo',   'kariouo',   167, NOW() - INTERVAL '3 days'  + INTERVAL '2h 45m',  9000),
        (s4, ch, '794077634', 'kariouo',   'kariouo',   134, NOW() - INTERVAL '1 day'   + INTERVAL '4h 00m', 16200),

        -- 封禁用戶佔位
        (s1, ch, 'REPLACE_WITH_BAN_USER_ID', 'banned_user', '封禁示範', 312, NOW() - INTERVAL '25 days' + INTERVAL '3h 40m', 13200),
        (s2, ch, 'REPLACE_WITH_BAN_USER_ID', 'banned_user', '封禁示範', 278, NOW() - INTERVAL '12 days' + INTERVAL '5h 00m', 18000),

        -- 超級聊天王：4 場全勤，超高時長
        (s1, ch, '77777771', 'power_chatter', '超級聊天王', 421, NOW() - INTERVAL '25 days' + INTERVAL '3h 50m', 14100),
        (s2, ch, '77777771', 'power_chatter', '超級聊天王', 389, NOW() - INTERVAL '12 days' + INTERVAL '5h 20m', 19500),
        (s3, ch, '77777771', 'power_chatter', '超級聊天王', 356, NOW() - INTERVAL '3 days'  + INTERVAL '2h 50m', 10500),
        (s4, ch, '77777771', 'power_chatter', '超級聊天王', 401, NOW() - INTERVAL '1 day'   + INTERVAL '5h 45m', 21300),

        -- 小奇點大戶：低留言但高時長（潛水捐贈型）
        (s2, ch, '77777772', 'bigbits_fan', '小奇點大戶', 45, NOW() - INTERVAL '12 days' + INTERVAL '2h 00m', 16800),
        (s4, ch, '77777772', 'bigbits_fan', '小奇點大戶', 23, NOW() - INTERVAL '1 day'   + INTERVAL '1h 30m', 14400)
    ON CONFLICT (session_id, user_id) DO UPDATE SET
        watch_seconds = EXCLUDED.watch_seconds;

    -- ── Stream events ─────────────────────────────────────────
    INSERT INTO stream_events
        (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
    VALUES
        (s3, ch, 'follow', '1075248331', 'capoo_xiang', '_咖波波_',  NULL,
         NOW() - INTERVAL '3 days'  + INTERVAL '45m'),
        (s2, ch, 'follow', '35760596',   'm950101',     'M950101',   NULL,
         NOW() - INTERVAL '12 days' + INTERVAL '30m'),
        (s1, ch, 'follow', '21018499',   'iceice12',    '古月謠',    NULL,
         NOW() - INTERVAL '25 days' + INTERVAL '20m'),

        (s1, ch, 'subscribe', '109156102', 'san_mou',  '三毛毛毛',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '25 days' + INTERVAL '2h 10m'),
        (s2, ch, 'subscribe', '117691767', 'rexyz2z',  'rexyz2z',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '1h 45m'),
        (s3, ch, 'subscribe', '36128773',  'ola0323',  '歐拉今天不是很想練習',
         '{"tier":"2000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '3 days'  + INTERVAL '1h 20m'),

        (s1, ch, 'cheer', '109156102', 'san_mou', '三毛毛毛',
         '{"bits":500}'::jsonb,
         NOW() - INTERVAL '25 days' + INTERVAL '3h 00m'),
        (s2, ch, 'cheer', '109156102', 'san_mou', '三毛毛毛',
         '{"bits":1000}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '4h 30m'),
        (s3, ch, 'cheer', '117691767', 'rexyz2z', 'rexyz2z',
         '{"bits":100}'::jsonb,
         NOW() - INTERVAL '3 days'  + INTERVAL '2h 15m'),

        (s2, ch, 'raid', '145045273', 'ranamase', '天瀨らん',
         '{"viewers":45,"from_broadcaster_id":"145045273","from_broadcaster_name":"ranamase"}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '2h 00m'),

        -- hsuyi1222（想睡覺_）事件
        (s1, ch, 'follow',    '797358387', 'hsuyi1222', '想睡覺_',
         NULL,
         NOW() - INTERVAL '25 days' + INTERVAL '15m'),
        (s2, ch, 'subscribe', '797358387', 'hsuyi1222', '想睡覺_',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '1h 00m'),

        -- kariouo 事件（贈訂 + cheer）
        (s3, ch, 'follow',    '794077634', 'kariouo', 'kariouo',
         NULL,
         NOW() - INTERVAL '3 days'  + INTERVAL '10m'),
        (s4, ch, 'subscribe', '794077634', 'kariouo', 'kariouo',
         '{"tier":"2000","is_gift":true,"gift_count":5}'::jsonb,
         NOW() - INTERVAL '1 day'   + INTERVAL '2h 30m'),
        (s4, ch, 'cheer',     '794077634', 'kariouo', 'kariouo',
         '{"bits":5000}'::jsonb,
         NOW() - INTERVAL '1 day'   + INTERVAL '3h 15m'),

        -- 封禁用戶佔位事件（歷史活躍記錄；替換 user_id 為實際被封禁帳號）
        (s1, ch, 'follow',    'REPLACE_WITH_BAN_USER_ID', 'banned_user', '封禁示範',
         NULL,
         NOW() - INTERVAL '25 days' + INTERVAL '5m'),
        (s1, ch, 'subscribe', 'REPLACE_WITH_BAN_USER_ID', 'banned_user', '封禁示範',
         '{"tier":"1000","is_gift":false}'::jsonb,
         NOW() - INTERVAL '25 days' + INTERVAL '1h 00m'),
        (s2, ch, 'cheer',     'REPLACE_WITH_BAN_USER_ID', 'banned_user', '封禁示範',
         '{"bits":200}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '3h 00m'),

        -- 超級聊天王：follow + 大量 cheer（互動紀錄列表展示）
        (s1, ch, 'follow',    '77777771', 'power_chatter', '超級聊天王',
         NULL,
         NOW() - INTERVAL '25 days' + INTERVAL '3m'),
        (s2, ch, 'cheer',     '77777771', 'power_chatter', '超級聊天王',
         '{"bits":250}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '2h 00m'),
        (s3, ch, 'cheer',     '77777771', 'power_chatter', '超級聊天王',
         '{"bits":750}'::jsonb,
         NOW() - INTERVAL '3 days'  + INTERVAL '1h 30m'),
        (s4, ch, 'cheer',     '77777771', 'power_chatter', '超級聊天王',
         '{"bits":300}'::jsonb,
         NOW() - INTERVAL '1 day'   + INTERVAL '4h 00m'),

        -- 小奇點大戶：高額 cheer（total_bits 超過 1K → formatBits 顯示 K 格式）
        (s2, ch, 'follow',    '77777772', 'bigbits_fan',   '小奇點大戶',
         NULL,
         NOW() - INTERVAL '12 days' + INTERVAL '1m'),
        (s2, ch, 'cheer',     '77777772', 'bigbits_fan',   '小奇點大戶',
         '{"bits":50000}'::jsonb,
         NOW() - INTERVAL '12 days' + INTERVAL '1h 00m'),
        (s4, ch, 'cheer',     '77777772', 'bigbits_fan',   '小奇點大戶',
         '{"bits":25000}'::jsonb,
         NOW() - INTERVAL '1 day'   + INTERVAL '1h 00m')
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
