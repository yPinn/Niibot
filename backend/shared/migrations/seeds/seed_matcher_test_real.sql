SET client_encoding = 'UTF8';
INSERT INTO channels (channel_id, channel_name, enabled)
VALUES ('120247692', 'llazypilot', true)
ON CONFLICT (channel_id) DO UPDATE SET channel_name = 'llazypilot', enabled = true;

-- ============================================================
-- Matcher seed — 3 partner channels with pre-computed overlap data
-- Targets channel llazypilot (120247692) — owner account.
-- Safe to re-run (ON CONFLICT DO UPDATE / DO NOTHING).
--
-- Partner profiles (real Twitch user IDs):
--   145045273  ranamase    45 潛在 / 5 共同 / 10.0%   (高潛力, 晚間電競)
--   36128773   ola0323     23 潛在 / 12 共同 / 34.3%  (中重疊, 下午遊戲)
--   193691668  after_moon   8 潛在 / 2 共同 / 20.0%   (小頻道, 夜間聊天)
-- ============================================================
DO $$
DECLARE ch TEXT;
BEGIN
SELECT channel_id INTO ch
FROM channels
WHERE channel_name = 'llazypilot'
LIMIT 1;
IF ch IS NULL THEN RAISE EXCEPTION 'Channel llazypilot not found.'; END IF;

-- ── Summaries ─────────────────────────────────────────────────────────────
INSERT INTO channel_overlap_summary (
    home_channel_id, partner_channel_id, window_days,
    partner_unique_chatters, home_unique_chatters,
    shared_chatters, exclusive_to_partner, overlap_pct, computed_at
) VALUES
    (ch, '145045273', 30, 50, 20,  5, 45, 10.00, NOW()),
    (ch, '36128773',  30, 35, 20, 12, 23, 34.29, NOW()),
    (ch, '193691668', 30, 10, 20,  2,  8, 20.00, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, window_days) DO UPDATE SET
    partner_unique_chatters = EXCLUDED.partner_unique_chatters,
    home_unique_chatters    = EXCLUDED.home_unique_chatters,
    shared_chatters         = EXCLUDED.shared_chatters,
    exclusive_to_partner    = EXCLUDED.exclusive_to_partner,
    overlap_pct             = EXCLUDED.overlap_pct,
    computed_at             = NOW();

-- ── Viewers: 145045273 ranamase (大量潛在) ────────────────────────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾 (home_sessions > 0)
    (ch, '145045273', '794077634', 'kariouo',       'kariouo',             4, 120, 14400, NOW() - INTERVAL '5 days',  4,   635,  3.41, NOW()),
    (ch, '145045273', '117691767', 'rexyz2z',       'rexyz2z',             3,  85, 10800, NOW() - INTERVAL '7 days',  5,   856,  1.56, NOW()),
    (ch, '145045273', '77777771',  'power_chatter', '留言王',              8, 250, 28800, NOW() - INTERVAL '1 day',   8,  2917,  5.28, NOW()),
    (ch, '145045273', '77777775',  'sub_loyal',     '忠實訂閱者',          5, 130, 18000, NOW() - INTERVAL '3 days',  4,   364,  3.12, NOW()),
    (ch, '145045273', '77777774',  'lurk_master',   '靜默守望',            4,  25, 14400, NOW() - INTERVAL '4 days',  5,    35,  1.92, NOW()),
    -- 潛在觀眾 (home_sessions = 0) — 高分群
    (ch, '145045273', '88881001', 'night_watcher',  '夜貓子',   10, 420, 36000, NOW() - INTERVAL '1 day',   0, 0, 52.78, NOW()),
    (ch, '145045273', '88881002', 'chat_junkie',    '話癆',      8, 380, 28800, NOW() - INTERVAL '2 days',  0, 0, 43.45, NOW()),
    (ch, '145045273', '88881003', 'weekend_gamer',  '週末玩家',  7, 290, 25200, NOW() - INTERVAL '3 days',  0, 0, 37.82, NOW()),
    (ch, '145045273', '88881004', 'fps_king',       'FPS王',     6, 240, 21600, NOW() - INTERVAL '4 days',  0, 0, 31.56, NOW()),
    (ch, '145045273', '88881005', 'streamer_fan',   '打卡粉絲',  6, 180, 19800, NOW() - INTERVAL '2 days',  0, 0, 28.14, NOW()),
    (ch, '145045273', '88881006', 'lurker_pro',     '專業潛水',  5,  45, 18000, NOW() - INTERVAL '1 day',   0, 0, 19.88, NOW()),
    (ch, '145045273', '88881007', 'clip_collector', '剪輯控',    5, 210, 16200, NOW() - INTERVAL '5 days',  0, 0, 24.67, NOW()),
    (ch, '145045273', '88881008', 'meme_lord',      '梗圖王',    4, 320, 14400, NOW() - INTERVAL '6 days',  0, 0, 22.34, NOW()),
    (ch, '145045273', '88881009', 'game_expert',    '遊戲達人',  4, 180, 14400, NOW() - INTERVAL '3 days',  0, 0, 20.45, NOW()),
    (ch, '145045273', '88881010', 'sub_hunter',     '訂閱獵人',  4, 150, 12600, NOW() - INTERVAL '4 days',  0, 0, 18.23, NOW()),
    -- 潛在觀眾 — 中分群
    (ch, '145045273', '88881011', 'daily_viewer',   '每日觀眾',  3, 140, 10800, NOW() - INTERVAL '2 days',  0, 0, 16.12, NOW()),
    (ch, '145045273', '88881012', 'night_shift',    '夜班族',    3, 120, 10800, NOW() - INTERVAL '3 days',  0, 0, 15.45, NOW()),
    (ch, '145045273', '88881013', 'raid_buddy',     '揪團夥伴',  3,  90,  9000, NOW() - INTERVAL '8 days',  0, 0, 13.67, NOW()),
    (ch, '145045273', '88881014', 'casual_viewer',  '偶爾路過',  2,  80,  7200, NOW() - INTERVAL '5 days',  0, 0, 11.34, NOW()),
    (ch, '145045273', '88881015', 'hype_train',     '嗨趴',      2, 110,  7200, NOW() - INTERVAL '6 days',  0, 0, 11.78, NOW()),
    -- 潛在觀眾 — 低分群 (1 場次)
    (ch, '145045273', '88881016', 'viewer_016', NULL, 1, 45, 3600, NOW() - INTERVAL '10 days', 0, 0, 7.34, NOW()),
    (ch, '145045273', '88881017', 'viewer_017', NULL, 1, 30, 3600, NOW() - INTERVAL '12 days', 0, 0, 6.12, NOW()),
    (ch, '145045273', '88881018', 'viewer_018', NULL, 1, 20, 1800, NOW() - INTERVAL '14 days', 0, 0, 4.11, NOW()),
    (ch, '145045273', '88881019', 'viewer_019', NULL, 1, 15, 1800, NOW() - INTERVAL '16 days', 0, 0, 3.71, NOW()),
    (ch, '145045273', '88881020', 'viewer_020', NULL, 1, 10, 1200, NOW() - INTERVAL '18 days', 0, 0, 3.30, NOW()),
    (ch, '145045273', '88881021', 'viewer_021', NULL, 1,  8,  900, NOW() - INTERVAL '20 days', 0, 0, 3.14, NOW()),
    (ch, '145045273', '88881022', 'viewer_022', NULL, 1,  5,  600, NOW() - INTERVAL '22 days', 0, 0, 2.82, NOW()),
    (ch, '145045273', '88881023', 'viewer_023', NULL, 1,  3,  600, NOW() - INTERVAL '24 days', 0, 0, 2.60, NOW()),
    (ch, '145045273', '88881024', 'viewer_024', NULL, 1,  2,  300, NOW() - INTERVAL '26 days', 0, 0, 2.49, NOW()),
    (ch, '145045273', '88881025', 'viewer_025', NULL, 1,  1,  300, NOW() - INTERVAL '28 days', 0, 0, 2.30, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Viewers: 36128773 ola0323 (中等重疊) ──────────────────────────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾
    (ch, '36128773', '77777771',  'power_chatter', '留言王',     5, 200, 18000, NOW() - INTERVAL '1 day',   8, 2917, 5.90, NOW()),
    (ch, '36128773', '77777773',  'gift_whale',    '贈禮鯨魚',   3,  90, 10800, NOW() - INTERVAL '5 days',  3,  223, 2.83, NOW()),
    (ch, '36128773', '77777774',  'lurk_master',   '靜默守望',   4,  25, 14400, NOW() - INTERVAL '4 days',  5,   35, 1.92, NOW()),
    (ch, '36128773', '77777778',  'bits_sprinkler','小額撒幣',   3, 100,  9000, NOW() - INTERVAL '6 days',  3,  204, 2.91, NOW()),
    (ch, '36128773', '109156102', 'san_mou',       '三毛毛毛',   2,  70,  7200, NOW() - INTERVAL '8 days',  4,  482, 1.42, NOW()),
    (ch, '36128773', '77777779',  'late_joiner',   '後半場才來', 2,  45,  3600, NOW() - INTERVAL '5 days',  4,  196, 1.24, NOW()),
    (ch, '36128773', '35760596',  'm950101',       'M950101',    2,  60,  5400, NOW() - INTERVAL '7 days',  4,  363, 1.38, NOW()),
    (ch, '36128773', '65359374',  'luming1228',    '嚕嚕閔',     1,  30,  3600, NOW() - INTERVAL '9 days',  4,  268, 0.62, NOW()),
    (ch, '36128773', '77777776',  'casual_a',      '偶爾路過A',  1,  20,  1800, NOW() - INTERVAL '10 days', 2,   62, 0.57, NOW()),
    (ch, '36128773', '77777777',  'casual_b',      '偶爾路過B',  1,  15,  1800, NOW() - INTERVAL '12 days', 1,   19, 0.54, NOW()),
    (ch, '36128773', '1075248331','capoo_xiang',   '_咖波波_',   1,  10,  1800, NOW() - INTERVAL '4 days',  2,   41, 0.51, NOW()),
    (ch, '36128773', '117691767', 'rexyz2z',       'rexyz2z',    2,  55,  7200, NOW() - INTERVAL '6 days',  5,  856, 1.28, NOW()),
    -- 潛在觀眾 (home_sessions = 0)
    (ch, '36128773', '88882001', 'top_fan_p2',    '頭號粉',      9, 400, 32400, NOW() - INTERVAL '1 day',  0, 0, 49.12, NOW()),
    (ch, '36128773', '88882002', 'active_chatter','活躍聊天',    7, 310, 25200, NOW() - INTERVAL '2 days', 0, 0, 38.67, NOW()),
    (ch, '36128773', '88882003', 'game_fan',      '遊戲粉',      6, 220, 21600, NOW() - INTERVAL '4 days', 0, 0, 29.44, NOW()),
    (ch, '36128773', '88882004', 'quiet_viewer',  '安靜觀眾',    5,  40, 18000, NOW() - INTERVAL '3 days', 0, 0, 18.00, NOW()),
    (ch, '36128773', '88882005', 'weekend_only',  '週末才開',    4, 160, 14400, NOW() - INTERVAL '5 days', 0, 0, 20.34, NOW()),
    (ch, '36128773', '88882006', 'raid_fan',      '揪團愛好者',  3, 120, 10800, NOW() - INTERVAL '7 days', 0, 0, 15.23, NOW()),
    (ch, '36128773', '88882007', 'viewer_p2_07',  NULL,          2,  70,  5400, NOW() - INTERVAL '9 days', 0, 0,  9.45, NOW()),
    (ch, '36128773', '88882008', 'viewer_p2_08',  NULL,          2,  50,  3600, NOW() - INTERVAL '11 days',0, 0,  8.67, NOW()),
    (ch, '36128773', '88882009', 'viewer_p2_09',  NULL,          1,  40,  1800, NOW() - INTERVAL '13 days',0, 0,  6.23, NOW()),
    (ch, '36128773', '88882010', 'viewer_p2_10',  NULL,          1,  25,  1800, NOW() - INTERVAL '15 days',0, 0,  5.71, NOW()),
    (ch, '36128773', '88882011', 'viewer_p2_11',  NULL,          1,  15,   900, NOW() - INTERVAL '18 days',0, 0,  4.89, NOW()),
    (ch, '36128773', '88882012', 'viewer_p2_12',  NULL,          1,   8,   600, NOW() - INTERVAL '20 days',0, 0,  4.14, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Viewers: 193691668 after_moon (小頻道) ────────────────────────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾
    (ch, '193691668', '77777772', 'bigbits_fan',  '大奇點',  3, 45, 10800, NOW() - INTERVAL '3 days',  3,  99, 1.22, NOW()),
    (ch, '193691668', '21018499', 'iceice12',     '古月謠',  2, 15,  7200, NOW() - INTERVAL '9 days',  1,  12, 0.77, NOW()),
    -- 潛在觀眾
    (ch, '193691668', '88883001', 'small_fan_01', '小台粉01', 5, 180, 18000, NOW() - INTERVAL '2 days', 0, 0, 24.12, NOW()),
    (ch, '193691668', '88883002', 'small_fan_02', '小台粉02', 4, 120, 14400, NOW() - INTERVAL '4 days', 0, 0, 18.56, NOW()),
    (ch, '193691668', '88883003', 'small_fan_03', NULL,       3,  80,  9000, NOW() - INTERVAL '6 days', 0, 0, 13.34, NOW()),
    (ch, '193691668', '88883004', 'small_fan_04', NULL,       2,  50,  5400, NOW() - INTERVAL '8 days', 0, 0,  8.67, NOW()),
    (ch, '193691668', '88883005', 'viewer_s3_05', NULL,       1,  25,  1800, NOW() - INTERVAL '12 days',0, 0,  5.71, NOW()),
    (ch, '193691668', '88883006', 'viewer_s3_06', NULL,       1,  10,   900, NOW() - INTERVAL '15 days',0, 0,  4.14, NOW()),
    (ch, '193691668', '88883007', 'viewer_s3_07', NULL,       1,   5,   600, NOW() - INTERVAL '18 days',0, 0,  3.56, NOW()),
    (ch, '193691668', '88883008', 'viewer_s3_08', NULL,       1,   3,   300, NOW() - INTERVAL '20 days',0, 0,  2.93, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Stream sessions for partner channels (no FK constraint on channel_id) ─
-- 145045273 ranamase: 8 sessions — 電競晚間台 (Valorant + LoL, 約晚間 20-22 點)
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('145045273', NOW() - INTERVAL '82 days' + INTERVAL '20h', NOW() - INTERVAL '82 days' + INTERVAL '24h',  '連勝中！來看看', 'VALORANT'),
    ('145045273', NOW() - INTERVAL '75 days' + INTERVAL '21h', NOW() - INTERVAL '75 days' + INTERVAL '25h',  '衝鑽排位賽',    'VALORANT'),
    ('145045273', NOW() - INTERVAL '68 days' + INTERVAL '20h', NOW() - INTERVAL '68 days' + INTERVAL '23h',  '英雄聯盟練習',  'League of Legends'),
    ('145045273', NOW() - INTERVAL '60 days' + INTERVAL '22h', NOW() - INTERVAL '60 days' + INTERVAL '26h',  '週末連線',      'VALORANT'),
    ('145045273', NOW() - INTERVAL '45 days' + INTERVAL '21h', NOW() - INTERVAL '45 days' + INTERVAL '25h',  '晚間精華賽',    'VALORANT'),
    ('145045273', NOW() - INTERVAL '30 days' + INTERVAL '20h', NOW() - INTERVAL '30 days' + INTERVAL '24h',  'LoL 新版本初探', 'League of Legends'),
    ('145045273', NOW() - INTERVAL '15 days' + INTERVAL '21h', NOW() - INTERVAL '15 days' + INTERVAL '25h',  '衝排位不睡了',  'VALORANT'),
    ('145045273', NOW() - INTERVAL '5  days' + INTERVAL '20h', NOW() - INTERVAL '5  days' + INTERVAL '23h',  '週末排位日',    'VALORANT')
ON CONFLICT DO NOTHING;

-- 36128773 ola0323: 5 sessions — 下午休閒台 (Minecraft + Just Chatting, 約下午 14-17 點)
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('36128773', NOW() - INTERVAL '70 days' + INTERVAL '14h', NOW() - INTERVAL '70 days' + INTERVAL '18h',  '蓋城計畫 Day1',   'Minecraft'),
    ('36128773', NOW() - INTERVAL '55 days' + INTERVAL '15h', NOW() - INTERVAL '55 days' + INTERVAL '20h',  '閒聊下午場',      'Just Chatting'),
    ('36128773', NOW() - INTERVAL '40 days' + INTERVAL '14h', NOW() - INTERVAL '40 days' + INTERVAL '18h',  'MC 生存模式',     'Minecraft'),
    ('36128773', NOW() - INTERVAL '20 days' + INTERVAL '16h', NOW() - INTERVAL '20 days' + INTERVAL '21h',  '週末放鬆聊',      'Just Chatting'),
    ('36128773', NOW() - INTERVAL '8  days' + INTERVAL '15h', NOW() - INTERVAL '8  days' + INTERVAL '19h',  'Minecraft 建築賽', 'Minecraft')
ON CONFLICT DO NOTHING;

-- 193691668 after_moon: 3 sessions — 深夜聊天小台 (Just Chatting, 約夜間 22-23 點)
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('193691668', NOW() - INTERVAL '50 days' + INTERVAL '22h', NOW() - INTERVAL '50 days' + INTERVAL '25h',  '深夜聊聊天',    'Just Chatting'),
    ('193691668', NOW() - INTERVAL '25 days' + INTERVAL '23h', NOW() - INTERVAL '25 days' + INTERVAL '26h',  '半夜睡不著',    'Just Chatting'),
    ('193691668', NOW() - INTERVAL '10 days' + INTERVAL '22h', NOW() - INTERVAL '10 days' + INTERVAL '24h',  '夜貓子集合',    'Just Chatting')
ON CONFLICT DO NOTHING;

RAISE NOTICE 'Matcher seed OK — home: %  partners: 145045273/ranamase(50,8s) 36128773/ola0323(35,5s) 193691668/after_moon(10,3s)', ch;
END;
$$;
