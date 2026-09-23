-- 135: playback facts and anonymous Video Queue rankings.
--
-- Queue promotion is not proof that media played. The overlay reports a
-- separate, idempotent playback-start fact: controlled players can confirm
-- playback, while iframe-only providers can record a clearly-labelled
-- best-effort start. Preview mode never calls the reporting endpoint.

ALTER TABLE video_queue
    ADD COLUMN IF NOT EXISTS playback_started_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS playback_signal TEXT,
    ADD COLUMN IF NOT EXISTS end_reason TEXT,
    ADD COLUMN IF NOT EXISTS played_seconds INTEGER;

ALTER TABLE video_queue
    DROP CONSTRAINT IF EXISTS chk_video_queue_playback_signal,
    DROP CONSTRAINT IF EXISTS chk_video_queue_end_reason,
    DROP CONSTRAINT IF EXISTS chk_video_queue_played_seconds;

ALTER TABLE video_queue
    ADD CONSTRAINT chk_video_queue_playback_signal
        CHECK (playback_signal IS NULL OR playback_signal IN ('confirmed', 'best_effort')),
    ADD CONSTRAINT chk_video_queue_end_reason
        CHECK (
            end_reason IS NULL OR end_reason IN (
                'completed', 'provider_error', 'autoplay_blocked', 'startup_timeout',
                'dashboard_skip', 'play_now', 'removed', 'cleared'
            )
        ),
    ADD CONSTRAINT chk_video_queue_played_seconds
        CHECK (played_seconds IS NULL OR played_seconds >= 0);

-- Partial indexes keep the normal queue-write path compact and serve the two
-- fixed ranking scopes without indexing rows that never started playback.
CREATE INDEX IF NOT EXISTS idx_video_queue_rankings_global
    ON video_queue (playback_started_at DESC, video_type, video_id)
    WHERE playback_started_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_video_queue_rankings_channel
    ON video_queue (channel_id, playback_started_at DESC, video_type, video_id)
    WHERE playback_started_at IS NOT NULL;

-- A native id is not globally unique across providers. New operational blocks
-- can be scoped to their provider; existing rows remain NULL wildcards so the
-- migration does not silently weaken a channel's moderation rules.
ALTER TABLE video_queue_blocklist
    ADD COLUMN IF NOT EXISTS video_type TEXT;

ALTER TABLE video_queue_blocklist
    DROP CONSTRAINT IF EXISTS chk_video_queue_blocklist_video_type;

ALTER TABLE video_queue_blocklist
    ADD CONSTRAINT chk_video_queue_blocklist_video_type
        CHECK (
            video_type IS NULL OR (
                kind IN ('video', 'creator')
                AND video_type IN (
                    'youtube', 'twitch_clip', 'twitch_vod', 'bilibili', 'instagram_reel'
                )
            )
        );

DROP INDEX IF EXISTS idx_video_queue_blocklist_unique;

CREATE UNIQUE INDEX idx_video_queue_blocklist_unique
    ON video_queue_blocklist (
        channel_id,
        kind,
        lower(value),
        (COALESCE(video_type, '*'))
    );
