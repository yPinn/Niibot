-- Insert test analytics data for testing
-- 使用 WITH 子句來正確處理 session_id

-- 1. 插入測試直播場次並獲取 ID
WITH inserted_sessions AS (
    INSERT INTO stream_sessions (channel_id, started_at, ended_at, title, game_name)
    VALUES
        ('120247692', NOW() - INTERVAL '3 hours', NOW(), 'Test Stream 1', 'Just Chatting'),
        ('120247692', NOW() - INTERVAL '1 day', NOW() - INTERVAL '1 day' + INTERVAL '2 hours', 'Test Stream 2', 'League of Legends')
    RETURNING id, channel_id, started_at
),
-- 2. 插入指令統計數據
inserted_commands AS (
    INSERT INTO command_stats (session_id, channel_id, command_name, usage_count, last_used_at)
    SELECT
        s.id,
        s.channel_id,
        c.command_name,
        c.usage_count,
        c.last_used_at
    FROM inserted_sessions s
    CROSS JOIN (
        VALUES
            ('!hi', 25, NOW() - INTERVAL '1 hour'),
            ('!help', 18, NOW() - INTERVAL '2 hours'),
            ('!uptime', 12, NOW() - INTERVAL '30 minutes'),
            ('!ai', 8, NOW() - INTERVAL '1.5 hours'),
            ('!運勢', 15, NOW() - INTERVAL '45 minutes')
    ) AS c(command_name, usage_count, last_used_at)
    WHERE s.started_at > NOW() - INTERVAL '12 hours'  -- 只對最新的 session
    RETURNING id
)
-- 3. 插入事件數據
INSERT INTO stream_events (session_id, channel_id, event_type, user_id, username, display_name, metadata, occurred_at)
SELECT
    s.id,
    s.channel_id,
    e.event_type,
    e.user_id,
    e.username,
    e.display_name,
    e.metadata,
    e.occurred_at
FROM inserted_sessions s
CROSS JOIN (
    VALUES
        ('follow', '12345', 'test_user1', 'Test User 1', NULL, NOW() - INTERVAL '2 hours'),
        ('follow', '12346', 'test_user2', 'Test User 2', NULL, NOW() - INTERVAL '1.5 hours'),
        ('subscribe', '12347', 'test_subscriber', 'Test Sub', '{"tier": "1000", "is_gift": false}'::jsonb, NOW() - INTERVAL '1 hour')
) AS e(event_type, user_id, username, display_name, metadata, occurred_at)
WHERE s.started_at > NOW() - INTERVAL '12 hours';  -- 只對最新的 session

-- 查詢驗證
SELECT 'Sessions created:' as info, COUNT(*) as count FROM stream_sessions WHERE channel_id = '120247692';
SELECT 'Commands created:' as info, COUNT(*) as count FROM command_stats WHERE channel_id = '120247692';
SELECT 'Events created:' as info, COUNT(*) as count FROM stream_events WHERE channel_id = '120247692';

-- 查看 Top Commands
SELECT command_name, SUM(usage_count) as total_usage
FROM command_stats
WHERE channel_id = '120247692'
GROUP BY command_name
ORDER BY total_usage DESC;

-- 查看最近的 sessions
SELECT id, title, started_at, ended_at,
       EXTRACT(EPOCH FROM (COALESCE(ended_at, NOW()) - started_at))/3600 as duration_hours
FROM stream_sessions
WHERE channel_id = '120247692'
ORDER BY started_at DESC;
