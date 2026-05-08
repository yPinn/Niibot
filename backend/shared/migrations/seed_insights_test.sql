-- ============================================================
-- Insights test seed v2 — 8 sessions · 20 users · expanded events
-- Uses the first enabled channel automatically.
-- Safe to re-run (ON CONFLICT DO NOTHING on all detail tables).
--
-- Session durations (for watch_seconds cap reference):
--   s1 60d  3h30m = 12600s    s5 18d  4h00m = 14400s
--   s2 45d  4h00m = 14400s    s6 12d  5h30m = 19800s
--   s3 35d  5h00m = 18000s    s7  3d  3h00m = 10800s
--   s4 25d  4h00m = 14400s    s8  1d  6h00m = 21600s
--
-- Identity constraints enforced here:
--   hsuyi1222  797358387 → MOD only  (API role; NOT VIP)
--   kariouo    794077634 → VIP only  (API role; NOT MOD)
--   Mod and VIP are mutually exclusive on Twitch.
-- ============================================================
DO $$
DECLARE ch TEXT;
s1 INT;
s2 INT;
s3 INT;
s4 INT;
s5 INT;
s6 INT;
s7 INT;
s8 INT;
BEGIN
SELECT channel_id INTO ch
FROM channels
WHERE channel_name = 'llazypilot'
LIMIT 1;
IF ch IS NULL THEN RAISE EXCEPTION 'Channel llazypilot not found.';
END IF;
-- ── Sessions ──────────────────────────────────────────────────────────────
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '60 days',
        NOW() - INTERVAL '60 days' + INTERVAL '3 hours 30 minutes',
        'Chill 放鬆日',
        'Just Chatting'
    )
RETURNING id INTO s1;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '45 days',
        NOW() - INTERVAL '45 days' + INTERVAL '4 hours',
        '練習賽直播',
        'League of Legends'
    )
RETURNING id INTO s2;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '35 days',
        NOW() - INTERVAL '35 days' + INTERVAL '5 hours',
        '晚間遊戲',
        'Minecraft'
    )
RETURNING id INTO s3;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '25 days',
        NOW() - INTERVAL '25 days' + INTERVAL '4 hours',
        'Late Night Gaming',
        'Stardew Valley'
    )
RETURNING id INTO s4;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '18 days',
        NOW() - INTERVAL '18 days' + INTERVAL '4 hours',
        '週末下午場',
        'Valorant'
    )
RETURNING id INTO s5;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '12 days',
        NOW() - INTERVAL '12 days' + INTERVAL '5 hours 30 minutes',
        '周末放鬆直播',
        'Minecraft'
    )
RETURNING id INTO s6;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '3 days',
        NOW() - INTERVAL '3 days' + INTERVAL '3 hours',
        '新遊戲初見',
        'Hollow Knight'
    )
RETURNING id INTO s7;
INSERT INTO stream_sessions (
        channel_id,
        started_at,
        ended_at,
        title,
        game_name
    )
VALUES (
        ch,
        NOW() - INTERVAL '1 day',
        NOW() - INTERVAL '1 day' + INTERVAL '6 hours',
        '週年慶特別直播',
        'Just Chatting'
    )
RETURNING id INTO s8;
-- ── Chatter stats ─────────────────────────────────────────────────────────
-- Real Twitch accounts:
--   36128773   ola0323       高活躍，tier-2 訂閱，全勤
--   117691767  rexyz2z       中活躍，tier-1 訂閱，有 cheer
--   65359374   luming1228    普通觀眾
--   1075248331 capoo_xiang   2024 新帳號，近期才加入
--   109156102  san_mou       合作夥伴，常 cheer
--   21018499   iceice12      2011 老帳號，超級潛水
--   35760596   m950101       affiliate，中等活躍
--   193691668  after_moon    高活躍聊天
--   797358387  hsuyi1222     頻道管理員 (MOD)  ← NOT VIP
--   794077634  kariouo       VIP               ← NOT MOD
--
    -- Fake accounts (77777771–77777779):
--   77777771   power_chatter 留言王，全勤
--   77777772   bigbits_fan   低留言高時長，大額 cheer
--   77777773   gift_whale    大量贈禮訂閱
--   77777774   lurk_master   靜默守望，極高時長幾乎不留言
--   77777775   sub_loyal     忠實訂閱者，穩定出席
--   77777776   casual_a      偶爾出現
--   77777777   casual_b      單次出沒
--   77777778   bits_sprinkler 小額多次 cheer
--   77777779   late_joiner   後半場才來，時長短
--
    -- Banned placeholder: 99999999
INSERT INTO chatter_stats (
        session_id,
        channel_id,
        user_id,
        username,
        display_name,
        message_count,
        last_message_at,
        watch_seconds
    )
VALUES -- ola0323 — 全勤 8 場
    (
        s1,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        280,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 20m',
        11800
    ),
    (
        s2,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        245,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 50m',
        13500
    ),
    (
        s3,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        310,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 50m',
        17200
    ),
    (
        s4,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        312,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 55m',
        13500
    ),
    (
        s5,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        198,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 50m',
        13200
    ),
    (
        s6,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        287,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 20m',
        18600
    ),
    (
        s7,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        198,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 50m',
        9900
    ),
    (
        s8,
        ch,
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        325,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 50m',
        20500
    ),
    -- power_chatter — 留言王，全勤 8 場
    (
        s1,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        380,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 25m',
        12100
    ),
    (
        s2,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        355,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 55m',
        14000
    ),
    (
        s3,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        420,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 55m',
        17500
    ),
    (
        s4,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        421,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 50m',
        14100
    ),
    (
        s5,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        395,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 55m',
        14000
    ),
    (
        s6,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        389,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 20m',
        19500
    ),
    (
        s7,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        356,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 50m',
        10500
    ),
    (
        s8,
        ch,
        '77777771',
        'power_chatter',
        '超級聊天王',
        401,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 45m',
        21300
    ),
    -- hsuyi1222 — MOD（API 賦予；資料庫不存身分，不得同時為 VIP）
    (
        s1,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        185,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 10m',
        12000
    ),
    (
        s2,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        160,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 50m',
        13800
    ),
    (
        s4,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        203,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 30m',
        13800
    ),
    (
        s5,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        220,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 55m',
        14000
    ),
    (
        s6,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        145,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 15m',
        19500
    ),
    (
        s8,
        ch,
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        89,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 30m',
        20400
    ),
    -- kariouo — VIP（API 賦予；不得同時為 MOD）
    (
        s5,
        ch,
        '794077634',
        'kariouo',
        'kariouo',
        145,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 30m',
        12600
    ),
    (
        s6,
        ch,
        '794077634',
        'kariouo',
        'kariouo',
        189,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 00m',
        18000
    ),
    (
        s7,
        ch,
        '794077634',
        'kariouo',
        'kariouo',
        167,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 45m',
        9000
    ),
    (
        s8,
        ch,
        '794077634',
        'kariouo',
        'kariouo',
        134,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 00m',
        16200
    ),
    -- rexyz2z — 中等活躍，tier-1 訂閱
    (
        s1,
        ch,
        '117691767',
        'rexyz2z',
        'rexyz2z',
        120,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 00m',
        10200
    ),
    (
        s2,
        ch,
        '117691767',
        'rexyz2z',
        'rexyz2z',
        145,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 30m',
        10800
    ),
    (
        s4,
        ch,
        '117691767',
        'rexyz2z',
        'rexyz2z',
        212,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 45m',
        13500
    ),
    (
        s6,
        ch,
        '117691767',
        'rexyz2z',
        'rexyz2z',
        178,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 00m',
        15300
    ),
    (
        s8,
        ch,
        '117691767',
        'rexyz2z',
        'rexyz2z',
        201,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 30m',
        19800
    ),
    -- san_mou — 合作夥伴，常帶 cheer
    (
        s1,
        ch,
        '109156102',
        'san_mou',
        '三毛毛毛',
        178,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 15m',
        11500
    ),
    (
        s3,
        ch,
        '109156102',
        'san_mou',
        '三毛毛毛',
        91,
        NOW() - INTERVAL '35 days' + INTERVAL '2h 40m',
        8700
    ),
    (
        s4,
        ch,
        '109156102',
        'san_mou',
        '三毛毛毛',
        135,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 45m',
        12300
    ),
    (
        s7,
        ch,
        '109156102',
        'san_mou',
        '三毛毛毛',
        78,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 30m',
        8100
    ),
    -- after_moon — 近期高活躍
    (
        s3,
        ch,
        '193691668',
        'after_moon',
        '午後的月亮',
        198,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 50m',
        17400
    ),
    (
        s4,
        ch,
        '193691668',
        'after_moon',
        '午後的月亮',
        167,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 50m',
        13800
    ),
    (
        s5,
        ch,
        '193691668',
        'after_moon',
        '午後的月亮',
        210,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 55m',
        14000
    ),
    (
        s6,
        ch,
        '193691668',
        'after_moon',
        '午後的月亮',
        256,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 25m',
        19200
    ),
    -- luming1228 — 普通觀眾
    (
        s2,
        ch,
        '65359374',
        'luming1228',
        '嚕嚕閔',
        88,
        NOW() - INTERVAL '45 days' + INTERVAL '4h 10m',
        9600
    ),
    (
        s4,
        ch,
        '65359374',
        'luming1228',
        '嚕嚕閔',
        54,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 00m',
        6600
    ),
    (
        s5,
        ch,
        '65359374',
        'luming1228',
        '嚕嚕閔',
        72,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 00m',
        9000
    ),
    (
        s7,
        ch,
        '65359374',
        'luming1228',
        '嚕嚕閔',
        54,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 00m',
        6600
    ),
    -- m950101 — 中等活躍，近期穩定出席
    (
        s2,
        ch,
        '35760596',
        'm950101',
        'M950101',
        67,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 20m',
        8700
    ),
    (
        s4,
        ch,
        '35760596',
        'm950101',
        'M950101',
        89,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 55m',
        9300
    ),
    (
        s7,
        ch,
        '35760596',
        'm950101',
        'M950101',
        95,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 50m',
        9600
    ),
    (
        s8,
        ch,
        '35760596',
        'm950101',
        'M950101',
        112,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 00m',
        14400
    ),
    -- bigbits_fan — 低留言高時長，大額 cheer（潛水捐贈型）
    (
        s2,
        ch,
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        45,
        NOW() - INTERVAL '45 days' + INTERVAL '2h 00m',
        12800
    ),
    (
        s5,
        ch,
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        31,
        NOW() - INTERVAL '18 days' + INTERVAL '1h 30m',
        12000
    ),
    (
        s8,
        ch,
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        23,
        NOW() - INTERVAL '1 day' + INTERVAL '1h 30m',
        14400
    ),
    -- gift_whale — 大量贈禮訂閱
    (
        s4,
        ch,
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        56,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 30m',
        9000
    ),
    (
        s6,
        ch,
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        78,
        NOW() - INTERVAL '12 days' + INTERVAL '4h 50m',
        17400
    ),
    (
        s8,
        ch,
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        89,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 30m',
        16200
    ),
    -- lurk_master — 超高時長極低留言（散佈圖底右角情境）
    (
        s1,
        ch,
        '77777774',
        'lurk_master',
        '靜默守望者',
        8,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 20m',
        12400
    ),
    (
        s2,
        ch,
        '77777774',
        'lurk_master',
        '靜默守望者',
        5,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 55m',
        14200
    ),
    (
        s3,
        ch,
        '77777774',
        'lurk_master',
        '靜默守望者',
        11,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 50m',
        17800
    ),
    (
        s5,
        ch,
        '77777774',
        'lurk_master',
        '靜默守望者',
        7,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 55m',
        14300
    ),
    (
        s6,
        ch,
        '77777774',
        'lurk_master',
        '靜默守望者',
        4,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 25m',
        19600
    ),
    -- sub_loyal — 忠實訂閱者，穩定出席
    (
        s3,
        ch,
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        89,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 30m',
        16200
    ),
    (
        s5,
        ch,
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        102,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 45m',
        13500
    ),
    (
        s7,
        ch,
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        78,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 45m',
        9900
    ),
    (
        s8,
        ch,
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        95,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 30m',
        16200
    ),
    -- iceice12 — 老帳號超級潛水（只出現一次）
    (
        s1,
        ch,
        '21018499',
        'iceice12',
        '古月謠',
        12,
        NOW() - INTERVAL '60 days' + INTERVAL '1h 05m',
        11400
    ),
    -- capoo_xiang — 新帳號，近期才加入
    (
        s7,
        ch,
        '1075248331',
        'capoo_xiang',
        '_咖波波_',
        23,
        NOW() - INTERVAL '3 days' + INTERVAL '1h 30m',
        3600
    ),
    (
        s8,
        ch,
        '1075248331',
        'capoo_xiang',
        '_咖波波_',
        18,
        NOW() - INTERVAL '1 day' + INTERVAL '2h 00m',
        7200
    ),
    -- casual_a — 偶爾路過，低活躍
    (
        s4,
        ch,
        '77777776',
        'casual_a',
        '偶爾路過A',
        34,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 00m',
        7200
    ),
    (
        s8,
        ch,
        '77777776',
        'casual_a',
        '偶爾路過A',
        28,
        NOW() - INTERVAL '1 day' + INTERVAL '3h 00m',
        10800
    ),
    -- casual_b — 只出現一次（測試單場情境）
    (
        s6,
        ch,
        '77777777',
        'casual_b',
        '偶爾路過B',
        19,
        NOW() - INTERVAL '12 days' + INTERVAL '2h 30m',
        5400
    ),
    -- bits_sprinkler — 小額但頻繁 cheer，中等活躍
    (
        s3,
        ch,
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        67,
        NOW() - INTERVAL '35 days' + INTERVAL '3h 30m',
        12600
    ),
    (
        s5,
        ch,
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        82,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 20m',
        12000
    ),
    (
        s6,
        ch,
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        55,
        NOW() - INTERVAL '12 days' + INTERVAL '4h 30m',
        16200
    ),
    -- late_joiner — 每次都後半場才來（時長短、留言集中在後段）
    (
        s5,
        ch,
        '77777779',
        'late_joiner',
        '後半場才來',
        45,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 55m',
        4200
    ),
    (
        s6,
        ch,
        '77777779',
        'late_joiner',
        '後半場才來',
        38,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 20m',
        3600
    ),
    (
        s7,
        ch,
        '77777779',
        'late_joiner',
        '後半場才來',
        52,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 50m',
        3900
    ),
    (
        s8,
        ch,
        '77777779',
        'late_joiner',
        '後半場才來',
        61,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 45m',
        5100
    ),
    -- banned_user — 封禁前有歷史活躍紀錄（替換佔位 ID 即可顯示封禁狀態）
    (
        s1,
        ch,
        '99999999',
        'banned_user',
        '封禁示範',
        312,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 40m',
        12200
    ),
    (
        s2,
        ch,
        '99999999',
        'banned_user',
        '封禁示範',
        278,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 50m',
        13800
    ),
    (
        s4,
        ch,
        '99999999',
        'banned_user',
        '封禁示範',
        156,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 00m',
        10800
    ) ON CONFLICT (session_id, user_id) DO
UPDATE
SET watch_seconds = EXCLUDED.watch_seconds;
-- ── Stream events ─────────────────────────────────────────────────────────
INSERT INTO stream_events (
        session_id,
        channel_id,
        event_type,
        user_id,
        username,
        display_name,
        metadata,
        occurred_at
    )
VALUES -- Follows
    (
        s1,
        ch,
        'follow',
        '21018499',
        'iceice12',
        '古月謠',
        NULL,
        NOW() - INTERVAL '60 days' + INTERVAL '20m'
    ),
    (
        s1,
        ch,
        'follow',
        '77777774',
        'lurk_master',
        '靜默守望者',
        NULL,
        NOW() - INTERVAL '60 days' + INTERVAL '5m'
    ),
    (
        s1,
        ch,
        'follow',
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        NULL,
        NOW() - INTERVAL '60 days' + INTERVAL '15m'
    ),
    (
        s2,
        ch,
        'follow',
        '35760596',
        'm950101',
        'M950101',
        NULL,
        NOW() - INTERVAL '45 days' + INTERVAL '30m'
    ),
    (
        s3,
        ch,
        'follow',
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        NULL,
        NOW() - INTERVAL '35 days' + INTERVAL '15m'
    ),
    (
        s3,
        ch,
        'follow',
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        NULL,
        NOW() - INTERVAL '35 days' + INTERVAL '8m'
    ),
    (
        s4,
        ch,
        'follow',
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        NULL,
        NOW() - INTERVAL '25 days' + INTERVAL '10m'
    ),
    (
        s4,
        ch,
        'follow',
        '77777776',
        'casual_a',
        '偶爾路過A',
        NULL,
        NOW() - INTERVAL '25 days' + INTERVAL '45m'
    ),
    (
        s5,
        ch,
        'follow',
        '794077634',
        'kariouo',
        'kariouo',
        NULL,
        NOW() - INTERVAL '18 days' + INTERVAL '5m'
    ),
    (
        s5,
        ch,
        'follow',
        '77777779',
        'late_joiner',
        '後半場才來',
        NULL,
        NOW() - INTERVAL '18 days' + INTERVAL '2h 10m'
    ),
    (
        s6,
        ch,
        'follow',
        '77777777',
        'casual_b',
        '偶爾路過B',
        NULL,
        NOW() - INTERVAL '12 days' + INTERVAL '1h 00m'
    ),
    (
        s7,
        ch,
        'follow',
        '1075248331',
        'capoo_xiang',
        '_咖波波_',
        NULL,
        NOW() - INTERVAL '3 days' + INTERVAL '45m'
    ),
    -- Subscribes — tier 1（自主）
    (
        s1,
        ch,
        'subscribe',
        '109156102',
        'san_mou',
        '三毛毛毛',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '60 days' + INTERVAL '2h 10m'
    ),
    (
        s2,
        ch,
        'subscribe',
        '117691767',
        'rexyz2z',
        'rexyz2z',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '1h 45m'
    ),
    (
        s2,
        ch,
        'subscribe',
        '797358387',
        'hsuyi1222',
        '想睡覺_',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '1h 00m'
    ),
    (
        s3,
        ch,
        'subscribe',
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '35 days' + INTERVAL '2h 00m'
    ),
    -- s7: ~32 days after first sub → valid monthly resub
    (
        s7,
        ch,
        'subscribe',
        '77777775',
        'sub_loyal',
        '忠實訂閱者',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '3 days' + INTERVAL '1h 30m'
    ),
    -- Subscribes — tier 2（自主）
    (
        s4,
        ch,
        'subscribe',
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        '{"tier":"2000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '25 days' + INTERVAL '1h 20m'
    ),
    (
        s8,
        ch,
        'subscribe',
        '36128773',
        'ola0323',
        '歐拉今天不是很想練習',
        '{"tier":"2000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '2h 00m'
    ),
    -- Subscribes — tier 3（自主；測試 tier3 顯示）
    (
        s8,
        ch,
        'subscribe',
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        '{"tier":"3000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '1h 00m'
    ),
    -- Gift subs — kariouo（VIP 身分大方贈禮）
    (
        s6,
        ch,
        'subscribe',
        '794077634',
        'kariouo',
        'kariouo',
        '{"tier":"1000","is_gift":true,"gift_count":5}'::jsonb,
        NOW() - INTERVAL '12 days' + INTERVAL '3h 00m'
    ),
    (
        s8,
        ch,
        'subscribe',
        '794077634',
        'kariouo',
        'kariouo',
        '{"tier":"2000","is_gift":true,"gift_count":5}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '2h 30m'
    ),
    -- Gift subs — gift_whale（大量贈禮情境）
    (
        s4,
        ch,
        'subscribe',
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        '{"tier":"1000","is_gift":true,"gift_count":10}'::jsonb,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 00m'
    ),
    (
        s6,
        ch,
        'subscribe',
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        '{"tier":"1000","is_gift":true,"gift_count":20}'::jsonb,
        NOW() - INTERVAL '12 days' + INTERVAL '4h 00m'
    ),
    (
        s8,
        ch,
        'subscribe',
        '77777773',
        'gift_whale',
        '贈禮鯨魚',
        '{"tier":"1000","is_gift":true,"gift_count":15}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '3h 00m'
    ),
    -- Cheers — san_mou（合作夥伴，階段性 cheer）
    (
        s1,
        ch,
        'cheer',
        '109156102',
        'san_mou',
        '三毛毛毛',
        '{"bits":500}'::jsonb,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 00m'
    ),
    (
        s3,
        ch,
        'cheer',
        '109156102',
        'san_mou',
        '三毛毛毛',
        '{"bits":1000}'::jsonb,
        NOW() - INTERVAL '35 days' + INTERVAL '2h 30m'
    ),
    (
        s4,
        ch,
        'cheer',
        '109156102',
        'san_mou',
        '三毛毛毛',
        '{"bits":2000}'::jsonb,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 30m'
    ),
    (
        s7,
        ch,
        'cheer',
        '109156102',
        'san_mou',
        '三毛毛毛',
        '{"bits":500}'::jsonb,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 00m'
    ),
    -- Cheers — bigbits_fan（大額，total_bits > 100K → formatCompact K 格式）
    (
        s2,
        ch,
        'cheer',
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        '{"bits":50000}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '1h 00m'
    ),
    (
        s5,
        ch,
        'cheer',
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        '{"bits":30000}'::jsonb,
        NOW() - INTERVAL '18 days' + INTERVAL '1h 00m'
    ),
    (
        s8,
        ch,
        'cheer',
        '77777772',
        'bigbits_fan',
        '小奇點大戶',
        '{"bits":20000}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '1h 00m'
    ),
    -- Cheers — power_chatter（留言王也 cheer）
    (
        s2,
        ch,
        'cheer',
        '77777771',
        'power_chatter',
        '超級聊天王',
        '{"bits":250}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '2h 00m'
    ),
    (
        s3,
        ch,
        'cheer',
        '77777771',
        'power_chatter',
        '超級聊天王',
        '{"bits":750}'::jsonb,
        NOW() - INTERVAL '35 days' + INTERVAL '3h 30m'
    ),
    (
        s6,
        ch,
        'cheer',
        '77777771',
        'power_chatter',
        '超級聊天王',
        '{"bits":500}'::jsonb,
        NOW() - INTERVAL '12 days' + INTERVAL '4h 00m'
    ),
    (
        s8,
        ch,
        'cheer',
        '77777771',
        'power_chatter',
        '超級聊天王',
        '{"bits":300}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 00m'
    ),
    -- Cheers — rexyz2z
    (
        s4,
        ch,
        'cheer',
        '117691767',
        'rexyz2z',
        'rexyz2z',
        '{"bits":100}'::jsonb,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 15m'
    ),
    (
        s8,
        ch,
        'cheer',
        '117691767',
        'rexyz2z',
        'rexyz2z',
        '{"bits":200}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '3h 00m'
    ),
    -- Cheers — bits_sprinkler（小額多次）
    (
        s3,
        ch,
        'cheer',
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        '{"bits":100}'::jsonb,
        NOW() - INTERVAL '35 days' + INTERVAL '1h 00m'
    ),
    (
        s5,
        ch,
        'cheer',
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        '{"bits":200}'::jsonb,
        NOW() - INTERVAL '18 days' + INTERVAL '2h 00m'
    ),
    (
        s6,
        ch,
        'cheer',
        '77777778',
        'bits_sprinkler',
        '小額撒幣',
        '{"bits":150}'::jsonb,
        NOW() - INTERVAL '12 days' + INTERVAL '3h 00m'
    ),
    -- Cheers — kariouo（VIP 大額 cheer）
    (
        s8,
        ch,
        'cheer',
        '794077634',
        'kariouo',
        'kariouo',
        '{"bits":5000}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '3h 15m'
    ),
    -- Raids（三場，規模遞增）
    (
        s2,
        ch,
        'raid',
        '145045273',
        'ranamase',
        '天瀨らん',
        '{"viewers":45,"from_broadcaster_id":"145045273","from_broadcaster_name":"ranamase"}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '2h 00m'
    ),
    (
        s5,
        ch,
        'raid',
        '88888881',
        'friendly_raider',
        '友情揪團',
        '{"viewers":28,"from_broadcaster_id":"88888881","from_broadcaster_name":"friendly_raider"}'::jsonb,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 00m'
    ),
    (
        s8,
        ch,
        'raid',
        '88888882',
        'mega_raider',
        '百人揪團',
        '{"viewers":120,"from_broadcaster_id":"88888882","from_broadcaster_name":"mega_raider"}'::jsonb,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 00m'
    ),
    -- banned_user — 封禁前歷史事件（替換 99999999 為實際帳號）
    (
        s1,
        ch,
        'follow',
        '99999999',
        'banned_user',
        '封禁示範',
        NULL,
        NOW() - INTERVAL '60 days' + INTERVAL '5m'
    ),
    (
        s1,
        ch,
        'subscribe',
        '99999999',
        'banned_user',
        '封禁示範',
        '{"tier":"1000","is_gift":false}'::jsonb,
        NOW() - INTERVAL '60 days' + INTERVAL '1h 00m'
    ),
    (
        s2,
        ch,
        'cheer',
        '99999999',
        'banned_user',
        '封禁示範',
        '{"bits":200}'::jsonb,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 00m'
    ) ON CONFLICT DO NOTHING;
-- ── Viewer channel status ──────────────────────────────────────────────────
-- Reflects current viewer roles / subscription state.
-- is_subscribed = TRUE only when last self-sub event is within ~30 days.
-- Gifted subs (gift_whale, kariouo) are outgoing gifts; those users
-- track total_gifts_given separately. Subscription recipients are not
-- tracked individually in this seed (real sync comes from Twitch API).
-- MOD/VIP are mutually exclusive on Twitch:
--   hsuyi1222 (797358387) = MOD only
--   kariouo   (794077634) = VIP only
INSERT INTO viewer_channel_status (
        channel_id, user_id, username, display_name,
        is_subscribed, sub_tier, sub_gifted,
        is_mod, is_vip, is_banned,
        follow_since, total_gifts_given, updated_at
    )
VALUES
    -- ola0323: tier-2 sub renewed s8 (1d ago = May 7) → still active
    (ch, '36128773',   'ola0323',        '歐拉今天不是很想練習',  TRUE,  '2', FALSE, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- rexyz2z: sub at s2 (45d ago) → expired
    (ch, '117691767',  'rexyz2z',        'Rexyz2z',              FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- luming1228: no sub
    (ch, '65359374',   'luming1228',     '嚕嚕閔',               FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- capoo_xiang: followed May 5, no sub
    (ch, '1075248331', 'capoo_xiang',    'capoo_xiang',          FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '3 days',                      0,  NOW()),
    -- san_mou: sub at s1 (60d ago) → expired
    (ch, '109156102',  'san_mou',        '三謀',                  FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- iceice12: old lurker, followed s1 era, no sub
    (ch, '21018499',   'iceice12',       'iceice12',             FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '60 days' + INTERVAL '5m',     0,  NOW()),
    -- m950101: followed s2 era, no sub
    (ch, '35760596',   'm950101',        'M950101',              FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '45 days' + INTERVAL '30m',    0,  NOW()),
    -- after_moon: no sub
    (ch, '193691668',  'after_moon',     '午後的月亮',            FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- hsuyi1222: MOD (NOT VIP); sub at s2 (45d) → expired
    (ch, '797358387',  'hsuyi1222',      'hsuyi1222',            FALSE, NULL, NULL, TRUE,  FALSE, FALSE, NOW() - INTERVAL '60 days' + INTERVAL '10m',   0,  NOW()),
    -- kariouo: VIP (NOT MOD); gifts 10 subs total, no self-sub
    (ch, '794077634',  'kariouo',        'kariouo',              FALSE, NULL, NULL, FALSE, TRUE,  FALSE, NOW() - INTERVAL '18 days' + INTERVAL '5m',    10, NOW()),
    -- power_chatter: no sub, old follower
    (ch, '77777771',   'power_chatter',  '留言王',               FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- bigbits_fan: no sub, old follower
    (ch, '77777772',   'bigbits_fan',    '大奇點',               FALSE, NULL, NULL, FALSE, FALSE, FALSE, NULL,                                           0,  NOW()),
    -- gift_whale: self-sub tier 3 at s8 (1d ago) → active; gifts 45 subs total
    (ch, '77777773',   'gift_whale',     '贈禮鯨魚',             TRUE,  '3', FALSE, FALSE, FALSE, FALSE, NOW() - INTERVAL '25 days' + INTERVAL '10m',   45, NOW()),
    -- lurk_master: followed s1 era, no sub
    (ch, '77777774',   'lurk_master',    '靜默守望',             FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '60 days' + INTERVAL '3m',    0,  NOW()),
    -- sub_loyal: self-sub tier 1 at s7 (3d ago = May 5) → active; first sub s3 (35d ago = Apr 3)
    (ch, '77777775',   'sub_loyal',      '忠實訂閱者',           TRUE,  '1', FALSE, FALSE, FALSE, FALSE, NOW() - INTERVAL '35 days' + INTERVAL '15m',   0,  NOW()),
    -- casual_a: followed s4 era, no sub
    (ch, '77777776',   'casual_a',       '偶爾路過A',            FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '25 days' + INTERVAL '45m',   0,  NOW()),
    -- casual_b: followed s6 era, no sub
    (ch, '77777777',   'casual_b',       '偶爾路過B',            FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '12 days' + INTERVAL '34m',   0,  NOW()),
    -- bits_sprinkler: followed s3 era, no sub
    (ch, '77777778',   'bits_sprinkler', '小額撒幣',             FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '35 days' + INTERVAL '8m',    0,  NOW()),
    -- late_joiner: followed s5 era, no sub
    (ch, '77777779',   'late_joiner',    '後來才到',             FALSE, NULL, NULL, FALSE, FALSE, FALSE, NOW() - INTERVAL '18 days' + INTERVAL '44m',   0,  NOW()),
    -- banned placeholder: followed + subbed long ago, now banned
    (ch, '99999999', 'banned_user', '封禁示範', FALSE, NULL, NULL, FALSE, FALSE, TRUE,  NOW() - INTERVAL '60 days' + INTERVAL '2m',    0,  NOW())
ON CONFLICT (channel_id, user_id) DO UPDATE SET
    is_subscribed    = EXCLUDED.is_subscribed,
    sub_tier         = EXCLUDED.sub_tier,
    sub_gifted       = EXCLUDED.sub_gifted,
    is_mod           = EXCLUDED.is_mod,
    is_vip           = EXCLUDED.is_vip,
    is_banned        = EXCLUDED.is_banned,
    follow_since     = EXCLUDED.follow_since,
    total_gifts_given = EXCLUDED.total_gifts_given,
    updated_at       = EXCLUDED.updated_at;
-- ── Command stats ─────────────────────────────────────────────────────────
INSERT INTO command_stats (
        session_id,
        channel_id,
        command_name,
        usage_count,
        last_used_at
    )
VALUES (
        s1,
        ch,
        '!lurk',
        38,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 20m'
    ),
    (
        s1,
        ch,
        '!discord',
        15,
        NOW() - INTERVAL '60 days' + INTERVAL '3h 00m'
    ),
    (
        s1,
        ch,
        '!clip',
        9,
        NOW() - INTERVAL '60 days' + INTERVAL '2h 00m'
    ),
    (
        s2,
        ch,
        '!lurk',
        44,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 50m'
    ),
    (
        s2,
        ch,
        '!discord',
        20,
        NOW() - INTERVAL '45 days' + INTERVAL '3h 30m'
    ),
    (
        s2,
        ch,
        '!clip',
        13,
        NOW() - INTERVAL '45 days' + INTERVAL '2h 00m'
    ),
    (
        s3,
        ch,
        '!lurk',
        51,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 40m'
    ),
    (
        s3,
        ch,
        '!今日',
        18,
        NOW() - INTERVAL '35 days' + INTERVAL '2h 00m'
    ),
    (
        s3,
        ch,
        '!clip',
        22,
        NOW() - INTERVAL '35 days' + INTERVAL '4h 00m'
    ),
    (
        s4,
        ch,
        '!lurk',
        42,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 50m'
    ),
    (
        s4,
        ch,
        '!discord',
        18,
        NOW() - INTERVAL '25 days' + INTERVAL '3h 30m'
    ),
    (
        s4,
        ch,
        '!clip',
        11,
        NOW() - INTERVAL '25 days' + INTERVAL '2h 00m'
    ),
    (
        s5,
        ch,
        '!lurk',
        48,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 50m'
    ),
    (
        s5,
        ch,
        '!discord',
        22,
        NOW() - INTERVAL '18 days' + INTERVAL '3h 00m'
    ),
    (
        s5,
        ch,
        '!今日',
        12,
        NOW() - INTERVAL '18 days' + INTERVAL '1h 00m'
    ),
    (
        s6,
        ch,
        '!lurk',
        55,
        NOW() - INTERVAL '12 days' + INTERVAL '5h 10m'
    ),
    (
        s6,
        ch,
        '!discord',
        23,
        NOW() - INTERVAL '12 days' + INTERVAL '4h 50m'
    ),
    (
        s6,
        ch,
        '!今日',
        14,
        NOW() - INTERVAL '12 days' + INTERVAL '3h 00m'
    ),
    (
        s7,
        ch,
        '!lurk',
        38,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 40m'
    ),
    (
        s7,
        ch,
        '!clip',
        19,
        NOW() - INTERVAL '3 days' + INTERVAL '2h 20m'
    ),
    (
        s7,
        ch,
        '!discord',
        9,
        NOW() - INTERVAL '3 days' + INTERVAL '1h 00m'
    ),
    (
        s8,
        ch,
        '!lurk',
        62,
        NOW() - INTERVAL '1 day' + INTERVAL '5h 30m'
    ),
    (
        s8,
        ch,
        '!discord',
        31,
        NOW() - INTERVAL '1 day' + INTERVAL '4h 00m'
    ),
    (
        s8,
        ch,
        '!clip',
        28,
        NOW() - INTERVAL '1 day' + INTERVAL '3h 00m'
    ),
    (
        s8,
        ch,
        '!今日',
        17,
        NOW() - INTERVAL '1 day' + INTERVAL '2h 00m'
    ) ON CONFLICT (session_id, command_name) DO NOTHING;
-- ── Attendance streaks backfill ───────────────────────────────────────────
-- Clear any stale streak data for this channel and recompute from chatter_stats.
-- Computes both current streak (consecutive from latest session) and
-- best_streak (max streak group across all time) in a single pass.
DELETE FROM viewer_attendance_streaks WHERE channel_id = ch;
INSERT INTO viewer_attendance_streaks (channel_id, user_id, streak_count, best_streak, last_session_id, updated_at)
WITH
sessions_ranked AS (
    SELECT id, channel_id, started_at,
           ROW_NUMBER() OVER (PARTITION BY channel_id ORDER BY started_at ASC) AS session_num
    FROM stream_sessions WHERE ended_at IS NOT NULL AND channel_id = ch
),
attendance AS (
    SELECT cs.channel_id, cs.user_id, cs.session_id, sr.session_num
    FROM chatter_stats cs
    JOIN sessions_ranked sr ON sr.id = cs.session_id AND sr.channel_id = cs.channel_id
),
viewer_streaks AS (
    SELECT channel_id, user_id, session_id, session_num,
           session_num - ROW_NUMBER() OVER (PARTITION BY channel_id, user_id ORDER BY session_num) AS streak_group
    FROM attendance
),
viewer_latest AS (
    SELECT channel_id, user_id, MAX(session_num) AS last_session_num
    FROM attendance GROUP BY channel_id, user_id
),
latest_group AS (
    SELECT vs.channel_id, vs.user_id, vs.streak_group
    FROM viewer_streaks vs
    JOIN viewer_latest vl ON vl.channel_id = vs.channel_id AND vl.user_id = vs.user_id AND vl.last_session_num = vs.session_num
),
current_streak AS (
    SELECT vs.channel_id, vs.user_id, COUNT(*)::INT AS streak_count
    FROM viewer_streaks vs
    JOIN latest_group lg ON lg.channel_id = vs.channel_id AND lg.user_id = vs.user_id AND lg.streak_group = vs.streak_group
    GROUP BY vs.channel_id, vs.user_id
),
best_streak AS (
    SELECT channel_id, user_id, MAX(cnt)::INT AS best_streak
    FROM (SELECT channel_id, user_id, streak_group, COUNT(*) AS cnt FROM viewer_streaks GROUP BY channel_id, user_id, streak_group) g
    GROUP BY channel_id, user_id
),
last_session_ids AS (
    SELECT vs.channel_id, vs.user_id, vs.session_id
    FROM viewer_streaks vs
    JOIN viewer_latest vl ON vl.channel_id = vs.channel_id AND vl.user_id = vs.user_id AND vl.last_session_num = vs.session_num
)
SELECT cs.channel_id, cs.user_id, cs.streak_count, bs.best_streak, ls.session_id, NOW()
FROM current_streak cs
JOIN best_streak bs ON bs.channel_id = cs.channel_id AND bs.user_id = cs.user_id
JOIN last_session_ids ls ON ls.channel_id = cs.channel_id AND ls.user_id = cs.user_id
ON CONFLICT (channel_id, user_id) DO UPDATE SET
    streak_count    = EXCLUDED.streak_count,
    best_streak     = GREATEST(viewer_attendance_streaks.best_streak, EXCLUDED.best_streak),
    last_session_id = EXCLUDED.last_session_id,
    updated_at      = EXCLUDED.updated_at;
RAISE NOTICE 'Seed OK — channel: %  sessions: s1=% s2=% s3=% s4=% s5=% s6=% s7=% s8=%',
ch,
s1,
s2,
s3,
s4,
s5,
s6,
s7,
s8;
END;
$$;