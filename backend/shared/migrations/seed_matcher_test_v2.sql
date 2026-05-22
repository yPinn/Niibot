-- ============================================================
-- Matcher seed v2 — 4 new partner channels covering edge cases
-- Uses the first enabled channel as home_channel.
-- Safe to re-run (ON CONFLICT DO UPDATE / DO NOTHING).
--
-- Potential score formula:
--   (sessions*3 + LN(MAX(msgs,1))*1.5 + watch_hours*0.5)
--   * (1.0 if home_sessions=0, 0.5 if 1-2, 0.1 if 3+)
--
-- Partner profiles:
--   987654321  kramer_tw    72 潛在 / 8 共同 / 10.0%  (大台, 晚間FPS)
--   246813579  sakuratv     27 潛在 / 18 共同 / 40.0%  (中台, 下午動漫RPG)
--   135792468  chill_zone    9 潛在 / 11 共同 / 55.0%  (聊天台, 白天高重疊)
--   864209753  pro_gamer99   8 潛在 / 0 共同 / 0.0%   (小競技台, 零重疊)
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
-- Suitability = overlap_pct * LN(exclusive_to_partner + 1):
--   sakuratv:    40.0 * ln(28) = 133.3  ← highest
--   chill_zone:  55.0 * ln(10) = 126.6
--   kramer_tw:   10.0 * ln(73) =  42.9
--   pro_gamer99:  0.0 * ln(9)  =   0.0  ← edge case: no overlap signal
INSERT INTO channel_overlap_summary (
    home_channel_id, partner_channel_id, window_days,
    partner_unique_chatters, home_unique_chatters,
    shared_chatters, exclusive_to_partner, overlap_pct, computed_at
) VALUES
    (ch, '987654321', 30,  80, 20,  8, 72, 10.00, NOW()),
    (ch, '246813579', 30,  45, 20, 18, 27, 40.00, NOW()),
    (ch, '135792468', 30,  20, 20, 11,  9, 55.00, NOW()),
    (ch, '864209753', 30,   8, 20,  0,  8,  0.00, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, window_days) DO UPDATE SET
    partner_unique_chatters = EXCLUDED.partner_unique_chatters,
    home_unique_chatters    = EXCLUDED.home_unique_chatters,
    shared_chatters         = EXCLUDED.shared_chatters,
    exclusive_to_partner    = EXCLUDED.exclusive_to_partner,
    overlap_pct             = EXCLUDED.overlap_pct,
    computed_at             = NOW();

-- ── Viewers: 987654321 kramer_tw (大台FPS, 低重疊但大量潛在) ──────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾 (home_sessions >= 3, multiplier 0.1)
    (ch, '987654321', '77778001', 'clutch_king',  '逆轉王',    8, 300, 28800, NOW() - INTERVAL '1 day',   6, 1100, 3.66, NOW()),
    (ch, '987654321', '77778002', 'fps_veteran',  'FPS老兵',   6, 180, 21600, NOW() - INTERVAL '2 days',  4,  520, 2.87, NOW()),
    (ch, '987654321', '77778003', 'aim_trainer',  '練槍狂',    5, 150, 18000, NOW() - INTERVAL '3 days',  3,  380, 2.50, NOW()),
    (ch, '987654321', '77778004', 'night_apex',   '深夜Apex',  4,  80, 14400, NOW() - INTERVAL '4 days',  4,  210, 2.06, NOW()),
    (ch, '987654321', '77778005', 'eco_round',    '省錢局',    4, 100, 14400, NOW() - INTERVAL '5 days',  5,  290, 2.09, NOW()),
    (ch, '987654321', '77778006', 'tower_watch',  '塔台觀察員', 3,  60,  9000, NOW() - INTERVAL '8 days',  3,   95, 1.64, NOW()),
    -- 共同觀眾 (home_sessions 1-2, multiplier 0.5)
    (ch, '987654321', '77778007', 'combo_player', '連段高手',  2,  45,  7200, NOW() - INTERVAL '9 days',  2,   58, 6.35, NOW()),
    (ch, '987654321', '77778008', 'flash_point',  '閃光點',    1,  20,  3600, NOW() - INTERVAL '12 days', 1,   15, 4.00, NOW()),
    -- 潛在觀眾 (home_sessions = 0) — S 等 (score ≥ 60)
    (ch, '987654321', '88884001', 'headshot_pro',  '爆頭狙手',  15, 620, 54000, NOW() - INTERVAL '1 day',  0, 0, 62.20, NOW()),
    (ch, '987654321', '88884002', 'rank1_grinder', '衝榜機器',  12, 480, 43200, NOW() - INTERVAL '2 days', 0, 0, 51.25, NOW()),
    -- 潛在觀眾 — A 等 (score 40-59)
    (ch, '987654321', '88884003', 'clutch_fan',    '逆轉粉',    10, 380, 36000, NOW() - INTERVAL '3 days', 0, 0, 43.87, NOW()),
    (ch, '987654321', '88884004', 'stream_stalker','守播粉',     9, 300, 32400, NOW() - INTERVAL '1 day',  0, 0, 40.10, NOW()),
    (ch, '987654321', '88884005', 'hype_shot',     '嗨射',       8, 260, 28800, NOW() - INTERVAL '4 days', 0, 0, 36.49, NOW()),
    (ch, '987654321', '88884006', 'fps_only',      'FPS限定',    7, 230, 25200, NOW() - INTERVAL '2 days', 0, 0, 32.74, NOW()),
    (ch, '987654321', '88884007', 'aim_lab_user',  '練槍房常客', 7, 190, 25200, NOW() - INTERVAL '5 days', 0, 0, 32.39, NOW()),
    -- 潛在觀眾 — B 等 (score 20-39)
    (ch, '987654321', '88884008', 'rage_quit_er',  '暴怒退出王', 6, 200, 21600, NOW() - INTERVAL '6 days', 0, 0, 28.95, NOW()),
    (ch, '987654321', '88884009', 'smurf_acc',     '小號仔',     5, 170, 18000, NOW() - INTERVAL '7 days', 0, 0, 25.15, NOW()),
    (ch, '987654321', '88884010', 'one_trick_pony','單英雄廚',   5, 120, 18000, NOW() - INTERVAL '8 days', 0, 0, 24.60, NOW()),
    (ch, '987654321', '88884011', 'kill_feed',     '擊殺播報',   4, 150, 14400, NOW() - INTERVAL '5 days', 0, 0, 21.51, NOW()),
    (ch, '987654321', '88884012', 'bronze_elo',    '青銅段位',   4, 100, 14400, NOW() - INTERVAL '9 days', 0, 0, 20.91, NOW()),
    -- 潛在觀眾 — C 等 (score < 20)
    (ch, '987654321', '88884013', 'chat_lurker',   '聊天潛伏',   3, 130,  9000, NOW() - INTERVAL '4 days', 0, 0, 17.67, NOW()),
    (ch, '987654321', '88884014', 'scope_check',   '鏡頭確認',   3,  75,  7200, NOW() - INTERVAL '10 days',0, 0, 16.51, NOW()),
    (ch, '987654321', '88884015', 'off_angle',     '非常規角度', 2,  90,  7200, NOW() - INTERVAL '11 days',0, 0, 13.75, NOW()),
    (ch, '987654321', '88884016', 'bait_baiter',   '誘導反誘',   2,  65,  5400, NOW() - INTERVAL '8 days', 0, 0, 13.06, NOW()),
    (ch, '987654321', '88884017', 'viewer_kw_017', NULL,          1,  55,  3600, NOW() - INTERVAL '14 days',0, 0,  9.50, NOW()),
    (ch, '987654321', '88884018', 'viewer_kw_018', NULL,          1,  40,  3600, NOW() - INTERVAL '15 days',0, 0,  9.02, NOW()),
    (ch, '987654321', '88884019', 'viewer_kw_019', NULL,          1,  25,  1800, NOW() - INTERVAL '17 days',0, 0,  8.04, NOW()),
    (ch, '987654321', '88884020', 'viewer_kw_020', NULL,          1,  18,  1800, NOW() - INTERVAL '19 days',0, 0,  7.59, NOW()),
    (ch, '987654321', '88884021', 'viewer_kw_021', NULL,          1,  12,  1200, NOW() - INTERVAL '21 days',0, 0,  6.90, NOW()),
    (ch, '987654321', '88884022', 'viewer_kw_022', NULL,          1,   5,   900, NOW() - INTERVAL '23 days',0, 0,  5.54, NOW()),
    (ch, '987654321', '88884023', 'viewer_kw_023', NULL,          1,   3,   600, NOW() - INTERVAL '25 days',0, 0,  4.73, NOW()),
    (ch, '987654321', '88884024', 'viewer_kw_024', NULL,          1,   2,   300, NOW() - INTERVAL '27 days',0, 0,  3.58, NOW()),
    (ch, '987654321', '88884025', 'viewer_kw_025', NULL,          1,   1,   300, NOW() - INTERVAL '29 days',0, 0,  3.04, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Viewers: 246813579 sakuratv (中台RPG, 高重疊) ─────────────────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾 (home_sessions >= 3, multiplier 0.1) — 因高重疊共有 18 人
    (ch, '246813579', '77779001', 'anime_lore',   '動漫達人',  9, 350, 32400, NOW() - INTERVAL '1 day',   5, 920, 3.84, NOW()),
    (ch, '246813579', '77779002', 'rpg_grinder',  'RPG肝帝',   8, 280, 28800, NOW() - INTERVAL '2 days',  4, 640, 3.52, NOW()),
    (ch, '246813579', '77779003', 'story_simp',   '劇情控',    7, 220, 25200, NOW() - INTERVAL '3 days',  6, 800, 3.16, NOW()),
    (ch, '246813579', '77779004', 'ff16_fan',     'FF16粉',    6, 190, 21600, NOW() - INTERVAL '4 days',  3, 310, 2.78, NOW()),
    (ch, '246813579', '77779005', 'genshin_adept','原神特攻',  5, 150, 18000, NOW() - INTERVAL '5 days',  4, 445, 2.42, NOW()),
    (ch, '246813579', '77779006', 'healer_main',  '奶媽主力',  5, 120, 18000, NOW() - INTERVAL '6 days',  3, 218, 2.35, NOW()),
    (ch, '246813579', '77779007', 'ost_enjoyer',  '遊戲音樂控', 4, 100, 14400, NOW() - INTERVAL '7 days',  5, 380, 2.09, NOW()),
    (ch, '246813579', '77779008', 'dungeon_diver', '地下城探索',4,  80, 12600, NOW() - INTERVAL '8 days',  3, 175, 1.98, NOW()),
    (ch, '246813579', '77779009', 'side_quest',   '支線任務狂', 3,  90,  9000, NOW() - INTERVAL '9 days',  4, 266, 1.74, NOW()),
    (ch, '246813579', '77779010', 'speed_runner',  '快速通關',  3,  60,  9000, NOW() - INTERVAL '10 days', 3,  82, 1.62, NOW()),
    (ch, '246813579', '77779011', 'trophy_hunter', '獎盃獵人',  2,  70,  7200, NOW() - INTERVAL '11 days', 4, 193, 1.32, NOW()),
    (ch, '246813579', '77779012', 'waifu_guard',   '老婆守衛',  2,  55,  7200, NOW() - INTERVAL '5 days',  3,  97, 1.24, NOW()),
    -- 共同觀眾 (home_sessions 1-2, multiplier 0.5)
    (ch, '246813579', '77779013', 'chapter_viewer','章節觀察',  4, 110, 14400, NOW() - INTERVAL '4 days',  2, 124, 10.55, NOW()),
    (ch, '246813579', '77779014', 'lore_lurker',   '世界觀潛水', 3,  80,  9000, NOW() - INTERVAL '6 days',  1,  47,  8.38, NOW()),
    (ch, '246813579', '77779015', 'casual_rpg',   '休閒RPG',    2,  60,  5400, NOW() - INTERVAL '12 days', 2,  63,  6.60, NOW()),
    (ch, '246813579', '77779016', 'clip_fan',     '剪輯追粉',   2,  40,  5400, NOW() - INTERVAL '14 days', 1,  18,  6.21, NOW()),
    (ch, '246813579', '77779017', 'rare_visitor',  '稀客',       1,  30,  1800, NOW() - INTERVAL '16 days', 2,  11,  4.48, NOW()),
    (ch, '246813579', '77779018', 'first_timer',   '初訪者',     1,  15,  1800, NOW() - INTERVAL '18 days', 1,   6,  3.53, NOW()),
    -- 潛在觀眾 (home_sessions = 0) — 因 exclusive=27 僅列代表性資料
    (ch, '246813579', '88885001', 'top_rpg_fan',  'RPG頭號粉',  10, 420, 36000, NOW() - INTERVAL '1 day',  0, 0, 48.60, NOW()),
    (ch, '246813579', '88885002', 'anime_binger',  '動漫連播',   8, 340, 28800, NOW() - INTERVAL '2 days', 0, 0, 39.78, NOW()),
    (ch, '246813579', '88885003', 'plot_twist',    '劇情反轉',   7, 260, 25200, NOW() - INTERVAL '3 days', 0, 0, 34.41, NOW()),
    (ch, '246813579', '88885004', 'boss_fight',    '頭目戰看客', 6, 210, 21600, NOW() - INTERVAL '4 days', 0, 0, 29.98, NOW()),
    (ch, '246813579', '88885005', 'ff_veteran',    'FF系列老粉', 5, 180, 18000, NOW() - INTERVAL '5 days', 0, 0, 25.76, NOW()),
    (ch, '246813579', '88885006', 'genshin_whale', '原神鯨魚',   4, 140, 14400, NOW() - INTERVAL '6 days', 0, 0, 21.62, NOW()),
    (ch, '246813579', '88885007', 'isekai_viewer', '異世界觀眾', 3, 110,  9000, NOW() - INTERVAL '8 days', 0, 0, 17.51, NOW()),
    (ch, '246813579', '88885008', 'viewer_sk_008', NULL,          2,  75,  5400, NOW() - INTERVAL '10 days',0, 0, 12.99, NOW()),
    (ch, '246813579', '88885009', 'viewer_sk_009', NULL,          2,  50,  3600, NOW() - INTERVAL '12 days',0, 0, 11.92, NOW()),
    (ch, '246813579', '88885010', 'viewer_sk_010', NULL,          1,  45,  1800, NOW() - INTERVAL '14 days',0, 0,  8.81, NOW()),
    (ch, '246813579', '88885011', 'viewer_sk_011', NULL,          1,  28,  1800, NOW() - INTERVAL '16 days',0, 0,  8.18, NOW()),
    (ch, '246813579', '88885012', 'viewer_sk_012', NULL,          1,  15,   900, NOW() - INTERVAL '18 days',0, 0,  7.31, NOW()),
    (ch, '246813579', '88885013', 'viewer_sk_013', NULL,          1,   8,   600, NOW() - INTERVAL '21 days',0, 0,  6.29, NOW()),
    (ch, '246813579', '88885014', 'viewer_sk_014', NULL,          1,   4,   300, NOW() - INTERVAL '24 days',0, 0,  5.08, NOW()),
    (ch, '246813579', '88885015', 'viewer_sk_015', NULL,          1,   1,   300, NOW() - INTERVAL '27 days',0, 0,  3.04, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Viewers: 135792468 chill_zone (白天聊天台, 超高重疊) ──────────────────
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 共同觀眾 (home_sessions >= 3, multiplier 0.1) — 高重疊台 11 共同觀眾
    (ch, '135792468', '77779101', 'sofa_sitter',   '沙發族',    7, 240, 25200, NOW() - INTERVAL '1 day',   6, 730, 2.96, NOW()),
    (ch, '135792468', '77779102', 'tea_drinker',   '泡茶聊天',  6, 180, 21600, NOW() - INTERVAL '2 days',  5, 540, 2.65, NOW()),
    (ch, '135792468', '77779103', 'lunch_breaker', '午休族',    5, 130, 18000, NOW() - INTERVAL '3 days',  4, 350, 2.37, NOW()),
    (ch, '135792468', '77779104', 'wfh_watcher',   '遠距上班族', 5, 100, 18000, NOW() - INTERVAL '4 days',  3, 180, 2.28, NOW()),
    (ch, '135792468', '77779105', 'daily_chatter', '日常閒聊',   4,  90, 14400, NOW() - INTERVAL '5 days',  4, 290, 2.04, NOW()),
    (ch, '135792468', '77779106', 'advice_seeker', '求建議者',   3, 110,  9000, NOW() - INTERVAL '6 days',  5, 470, 1.77, NOW()),
    (ch, '135792468', '77779107', 'homework_bg',   '邊做功課',   3,  50,  9000, NOW() - INTERVAL '7 days',  3,  78, 1.52, NOW()),
    (ch, '135792468', '77779108', 'meme_sharer',   '梗圖分享者', 4, 160, 12600, NOW() - INTERVAL '3 days',  6, 890, 2.14, NOW()),
    -- 共同觀眾 (home_sessions 1-2, multiplier 0.5)
    (ch, '135792468', '77779109', 'weekend_drop',  '週末路過',   3,  70,  9000, NOW() - INTERVAL '8 days',  2,  55,  8.38, NOW()),
    (ch, '135792468', '77779110', 'once_visitor',  '曾經路人',   1,  25,  1800, NOW() - INTERVAL '15 days', 1,   8,  3.89, NOW()),
    (ch, '135792468', '77779111', 'new_joiner',    '新加入',     1,  10,   900, NOW() - INTERVAL '20 days', 2,  22,  3.05, NOW()),
    -- 潛在觀眾 (home_sessions = 0) — exclusive=9 全部列出
    (ch, '135792468', '88886001', 'morning_crowd', '早鳥族',     6, 200, 21600, NOW() - INTERVAL '1 day',  0, 0, 28.95, NOW()),
    (ch, '135792468', '88886002', 'afternoon_chill','下午悠閒',  5, 150, 18000, NOW() - INTERVAL '2 days', 0, 0, 24.76, NOW()),
    (ch, '135792468', '88886003', 'bg_noise_fan',  '背景音常客', 4, 100, 14400, NOW() - INTERVAL '3 days', 0, 0, 20.91, NOW()),
    (ch, '135792468', '88886004', 'intro_lurker',  '開播必潛',   3,  80,  9000, NOW() - INTERVAL '5 days', 0, 0, 16.78, NOW()),
    (ch, '135792468', '88886005', 'slow_chat',     '慢慢聊',     2,  60,  5400, NOW() - INTERVAL '7 days', 0, 0, 12.60, NOW()),
    (ch, '135792468', '88886006', 'viewer_cz_006', NULL,          2,  30,  3600, NOW() - INTERVAL '10 days',0, 0, 10.68, NOW()),
    (ch, '135792468', '88886007', 'viewer_cz_007', NULL,          1,  40,  1800, NOW() - INTERVAL '12 days',0, 0,  8.81, NOW()),
    (ch, '135792468', '88886008', 'viewer_cz_008', NULL,          1,  12,   900, NOW() - INTERVAL '16 days',0, 0,  6.63, NOW()),
    (ch, '135792468', '88886009', 'viewer_cz_009', NULL,          1,   3,   300, NOW() - INTERVAL '22 days',0, 0,  4.73, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Viewers: 864209753 pro_gamer99 (深夜競技, 零重疊邊界案例) ──────────────
-- overlap_pct = 0.0, suitability = 0 — 測試 UI 對零重疊頻道的顯示
INSERT INTO channel_overlap_viewers (
    home_channel_id, partner_channel_id, user_id, username, display_name,
    partner_sessions, partner_messages, partner_watch_sec, partner_last_seen,
    home_sessions, home_messages, potential_score, computed_at
) VALUES
    -- 潛在觀眾 (home_sessions = 0) — 全部為純潛在，無共同觀眾
    (ch, '864209753', '88887001', 'ow2_top500',    'OW2T500',    8, 310, 28800, NOW() - INTERVAL '2 days', 0, 0, 37.64, NOW()),
    (ch, '864209753', '88887002', 'apex_pred',     'Apex掠奪',   7, 250, 25200, NOW() - INTERVAL '3 days', 0, 0, 32.22, NOW()),
    (ch, '864209753', '88887003', 'nocturnal_gamer','深夜電競',  5, 180, 18000, NOW() - INTERVAL '5 days', 0, 0, 25.48, NOW()),
    (ch, '864209753', '88887004', 'insomniac_aim', '失眠練槍',   4, 120, 14400, NOW() - INTERVAL '7 days', 0, 0, 21.10, NOW()),
    (ch, '864209753', '88887005', 'midnight_rush', '午夜衝分',   3,  90,  9000, NOW() - INTERVAL '9 days', 0, 0, 16.75, NOW()),
    (ch, '864209753', '88887006', 'viewer_pg_006', NULL,          2,  60,  5400, NOW() - INTERVAL '12 days',0, 0, 12.60, NOW()),
    (ch, '864209753', '88887007', 'viewer_pg_007', NULL,          1,  35,  1800, NOW() - INTERVAL '18 days',0, 0,  8.57, NOW()),
    (ch, '864209753', '88887008', 'viewer_pg_008', NULL,          1,   8,   600, NOW() - INTERVAL '25 days',0, 0,  6.29, NOW())
ON CONFLICT (home_channel_id, partner_channel_id, user_id) DO UPDATE SET
    partner_sessions  = EXCLUDED.partner_sessions,
    partner_messages  = EXCLUDED.partner_messages,
    partner_watch_sec = EXCLUDED.partner_watch_sec,
    partner_last_seen = EXCLUDED.partner_last_seen,
    home_sessions     = EXCLUDED.home_sessions,
    home_messages     = EXCLUDED.home_messages,
    potential_score   = EXCLUDED.potential_score,
    computed_at       = NOW();

-- ── Stream sessions: 987654321 kramer_tw (10 sessions, 晚間 FPS, 20-23h) ──
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('987654321', NOW() - INTERVAL '88 days' + INTERVAL '20h', NOW() - INTERVAL '88 days' + INTERVAL '23h',  '初登場！衝分', 'VALORANT'),
    ('987654321', NOW() - INTERVAL '80 days' + INTERVAL '20h', NOW() - INTERVAL '80 days' + INTERVAL '24h',  '鑽石在眼前',   'VALORANT'),
    ('987654321', NOW() - INTERVAL '72 days' + INTERVAL '21h', NOW() - INTERVAL '72 days' + INTERVAL '25h',  'Apex 天梯戰',  'Apex Legends'),
    ('987654321', NOW() - INTERVAL '65 days' + INTERVAL '20h', NOW() - INTERVAL '65 days' + INTERVAL '23h',  '連勝串燒',     'VALORANT'),
    ('987654321', NOW() - INTERVAL '55 days' + INTERVAL '21h', NOW() - INTERVAL '55 days' + INTERVAL '24h',  '跨遊戲挑戰日', 'Apex Legends'),
    ('987654321', NOW() - INTERVAL '45 days' + INTERVAL '20h', NOW() - INTERVAL '45 days' + INTERVAL '23h',  '晚間精華賽',   'VALORANT'),
    ('987654321', NOW() - INTERVAL '35 days' + INTERVAL '21h', NOW() - INTERVAL '35 days' + INTERVAL '25h',  '破天荒逆轉',   'VALORANT'),
    ('987654321', NOW() - INTERVAL '25 days' + INTERVAL '20h', NOW() - INTERVAL '25 days' + INTERVAL '23h',  'Apex 新賽季',  'Apex Legends'),
    ('987654321', NOW() - INTERVAL '15 days' + INTERVAL '21h', NOW() - INTERVAL '15 days' + INTERVAL '25h',  '衝不睡了',     'VALORANT'),
    ('987654321', NOW() - INTERVAL '5  days' + INTERVAL '20h', NOW() - INTERVAL '5  days' + INTERVAL '24h',  '週末決勝局',   'VALORANT')
ON CONFLICT DO NOTHING;

-- ── Stream sessions: 246813579 sakuratv (6 sessions, 下午 RPG/動漫, 14-18h) ─
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('246813579', NOW() - INTERVAL '78 days' + INTERVAL '14h', NOW() - INTERVAL '78 days' + INTERVAL '19h',  'FF16 初見！序章激燃', 'Final Fantasy XVI'),
    ('246813579', NOW() - INTERVAL '60 days' + INTERVAL '15h', NOW() - INTERVAL '60 days' + INTERVAL '20h',  '原神 4.5 更新特輯',   'Genshin Impact'),
    ('246813579', NOW() - INTERVAL '45 days' + INTERVAL '14h', NOW() - INTERVAL '45 days' + INTERVAL '18h',  'FF16 二週目挑戰',     'Final Fantasy XVI'),
    ('246813579', NOW() - INTERVAL '30 days' + INTERVAL '15h', NOW() - INTERVAL '30 days' + INTERVAL '19h',  '原神 深境螺旋攻略',   'Genshin Impact'),
    ('246813579', NOW() - INTERVAL '15 days' + INTERVAL '14h', NOW() - INTERVAL '15 days' + INTERVAL '17h',  'FF16 DLC 首殺',       'Final Fantasy XVI'),
    ('246813579', NOW() - INTERVAL '5  days' + INTERVAL '15h', NOW() - INTERVAL '5  days' + INTERVAL '19h',  '週末動漫閒聊',        'Just Chatting')
ON CONFLICT DO NOTHING;

-- ── Stream sessions: 135792468 chill_zone (4 sessions, 白天聊天, 10-14h) ──
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('135792468', NOW() - INTERVAL '60 days' + INTERVAL '10h', NOW() - INTERVAL '60 days' + INTERVAL '14h',  '早晨開播！閒聊',      'Just Chatting'),
    ('135792468', NOW() - INTERVAL '40 days' + INTERVAL '11h', NOW() - INTERVAL '40 days' + INTERVAL '15h',  '上班族聊天室',        'Just Chatting'),
    ('135792468', NOW() - INTERVAL '20 days' + INTERVAL '10h', NOW() - INTERVAL '20 days' + INTERVAL '13h',  '週間下午場',          'Just Chatting'),
    ('135792468', NOW() - INTERVAL '7  days' + INTERVAL '11h', NOW() - INTERVAL '7  days' + INTERVAL '15h',  '日常快樂聊',          'Just Chatting')
ON CONFLICT DO NOTHING;

-- ── Stream sessions: 864209753 pro_gamer99 (3 sessions, 深夜競技, 23-03h) ─
INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
VALUES
    ('864209753', NOW() - INTERVAL '45 days' + INTERVAL '23h', NOW() - INTERVAL '44 days' + INTERVAL '3h',   '深夜 OW2 排位',       'Overwatch 2'),
    ('864209753', NOW() - INTERVAL '22 days' + INTERVAL '23h', NOW() - INTERVAL '21 days' + INTERVAL '4h',   'Apex 通宵練習',       'Apex Legends'),
    ('864209753', NOW() - INTERVAL '8  days' + INTERVAL '23h', NOW() - INTERVAL '7  days' + INTERVAL '3h',   '不打到天亮不甘心',     'Overwatch 2')
ON CONFLICT DO NOTHING;

RAISE NOTICE 'Matcher seed v2 OK — home: %  partners: 987654321/kramer_tw(80,10s) 246813579/sakuratv(45,6s) 135792468/chill_zone(20,4s) 864209753/pro_gamer99(8,3s)', ch;
END;
$$;
