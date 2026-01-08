-- Twitch Analytics Schema - MVP Edition
-- 專注於：指令統計 + 事件追蹤
-- 不包含：聊天訊息記錄、觀眾數追蹤（可日後擴充）

-- ============================================
-- 核心表
-- ============================================

-- 1. 直播場次
CREATE TABLE IF NOT EXISTS stream_sessions (
    id SERIAL PRIMARY KEY,
    channel_id TEXT NOT NULL,                   -- TwitchIO: payload.broadcaster.id
    started_at TIMESTAMPTZ NOT NULL,            -- TwitchIO: payload.started_at 或 NOW()
    ended_at TIMESTAMPTZ,                       -- Bot 設定，NULL = 進行中
    title TEXT,                                 -- TwitchIO: stream.title (可選)
    game_name TEXT,                             -- TwitchIO: stream.game_name (可選)
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. 指令使用統計（聚合設計，每場次每指令一筆）
CREATE TABLE IF NOT EXISTS command_stats (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,                   -- Bot context: ctx.channel.id
    command_name TEXT NOT NULL,                 -- Bot 解析: '!hi', '!ai', '!運勢'
    usage_count INT DEFAULT 1,                  -- Bot 累加
    last_used_at TIMESTAMPTZ NOT NULL,          -- Bot: NOW()
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(session_id, command_name)            -- 確保每場次每指令只有一筆
);

-- 3. 事件記錄（Follow, Subscribe, Raid）
CREATE TABLE IF NOT EXISTS stream_events (
    id SERIAL PRIMARY KEY,
    session_id INT NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
    channel_id TEXT NOT NULL,                   -- TwitchIO: payload.broadcaster.id
    event_type TEXT NOT NULL,                   -- Bot 判斷: 'follow', 'subscribe', 'raid'
    user_id TEXT,                               -- TwitchIO: payload.user.id
    username TEXT,                              -- TwitchIO: payload.user.name
    display_name TEXT,                          -- TwitchIO: payload.user.display_name
    metadata JSONB,                             -- 彈性欄位，見下方說明
    occurred_at TIMESTAMPTZ NOT NULL,           -- TwitchIO: payload.followed_at 或 NOW()
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (event_type IN ('follow', 'subscribe', 'raid'))
);

-- ============================================
-- 索引策略
-- ============================================

-- Session 索引
CREATE INDEX idx_sessions_channel_time
    ON stream_sessions(channel_id, started_at DESC);

CREATE INDEX idx_sessions_active
    ON stream_sessions(channel_id)
    WHERE ended_at IS NULL;

-- Command 索引
CREATE INDEX idx_cmd_session
    ON command_stats(session_id, usage_count DESC);

CREATE INDEX idx_cmd_channel_time
    ON command_stats(channel_id, last_used_at DESC);

-- Event 索引
CREATE INDEX idx_events_session
    ON stream_events(session_id, occurred_at);

CREATE INDEX idx_events_type
    ON stream_events(channel_id, event_type, occurred_at DESC);

-- ============================================
-- 查詢 View（提升 Dashboard 效能）
-- ============================================

-- Top Commands（每場次）
CREATE OR REPLACE VIEW v_top_commands AS
SELECT
    session_id,
    channel_id,
    command_name,
    usage_count,
    last_used_at
FROM command_stats
ORDER BY session_id DESC, usage_count DESC;

-- Session 統計摘要
CREATE OR REPLACE VIEW v_session_summary AS
SELECT
    s.id as session_id,
    s.channel_id,
    s.started_at,
    s.ended_at,
    s.title,
    s.game_name,
    EXTRACT(EPOCH FROM (COALESCE(s.ended_at, NOW()) - s.started_at))/3600 as duration_hours,
    COALESCE(SUM(c.usage_count), 0) as total_commands,
    COALESCE(SUM(CASE WHEN e.event_type = 'follow' THEN 1 END), 0) as new_follows,
    COALESCE(SUM(CASE WHEN e.event_type = 'subscribe' THEN 1 END), 0) as new_subs,
    COALESCE(SUM(CASE WHEN e.event_type = 'raid' THEN 1 END), 0) as raids_received
FROM stream_sessions s
LEFT JOIN command_stats c ON c.session_id = s.id
LEFT JOIN stream_events e ON e.session_id = s.id
GROUP BY s.id;

-- ============================================
-- metadata 欄位說明
-- ============================================

-- Follow 事件：
-- {}  (無額外資料)

-- Subscribe 事件：
-- {
--   "tier": "1000",      -- TwitchIO: payload.tier (1000/2000/3000)
--   "is_gift": false     -- TwitchIO: payload.is_gift
-- }

-- Raid 事件：
-- {
--   "viewers": 50,                       -- TwitchIO: payload.viewers
--   "from_broadcaster_id": "123456",     -- TwitchIO: payload.from_broadcaster.id
--   "from_broadcaster_name": "raider"    -- TwitchIO: payload.from_broadcaster.name
-- }

-- ============================================
-- 維護腳本（建議定期執行）
-- ============================================

-- 清理 90 天前的場次資料（會級聯刪除 command_stats 和 stream_events）
-- DELETE FROM stream_sessions WHERE started_at < NOW() - INTERVAL '90 days';

-- ============================================
-- 日後擴充方向
-- ============================================

-- Phase 2: 加入聊天統計
-- CREATE TABLE chat_activity (
--     session_id INT NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
--     user_id TEXT NOT NULL,
--     username TEXT NOT NULL,
--     message_count INT DEFAULT 1,
--     PRIMARY KEY (session_id, user_id)
-- );

-- Phase 3: 加入觀眾數追蹤
-- CREATE TABLE viewer_snapshots (
--     id SERIAL PRIMARY KEY,
--     session_id INT NOT NULL REFERENCES stream_sessions(id) ON DELETE CASCADE,
--     viewer_count INT NOT NULL,
--     snapshot_at TIMESTAMPTZ NOT NULL
-- );
