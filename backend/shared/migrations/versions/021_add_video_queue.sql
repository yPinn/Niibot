-- 021: Add video queue tables for YouTube song request feature

-- Step 1: Extend redemption_configs CHECK constraint to include 'video_queue'
ALTER TABLE redemption_configs
    DROP CONSTRAINT IF EXISTS redemption_configs_action_type_check;
ALTER TABLE redemption_configs
    ADD CONSTRAINT redemption_configs_action_type_check
    CHECK (action_type IN ('vip', 'first', 'niibot_auth', 'game_queue', 'video_queue'));

-- Step 2: Video queue entries table (FIFO queue)
CREATE TABLE IF NOT EXISTS video_queue (
    id                  BIGSERIAL PRIMARY KEY,
    channel_id          TEXT NOT NULL,
    video_id            TEXT NOT NULL,           -- YouTube 11-char ID
    title               TEXT,                    -- from YouTube Data API, nullable
    duration_seconds    INT,                     -- from YouTube Data API (or overlay fallback)
    requested_by        TEXT NOT NULL,           -- Twitch display_name
    source              TEXT NOT NULL DEFAULT 'chat'
                        CHECK (source IN ('chat', 'redemption')),
    status              TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued', 'playing', 'done', 'skipped')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ
);

-- Fast lookup for active entries by channel and status
CREATE INDEX IF NOT EXISTS idx_video_queue_channel_status
    ON video_queue (channel_id, status, created_at);

-- Step 3: Video queue settings table
CREATE TABLE IF NOT EXISTS video_queue_settings (
    channel_id              TEXT NOT NULL PRIMARY KEY,
    enabled                 BOOLEAN NOT NULL DEFAULT TRUE,
    min_role_chat           TEXT NOT NULL DEFAULT 'everyone'
                            CHECK (min_role_chat IN ('everyone', 'subscriber', 'vip', 'moderator', 'broadcaster')),
    max_duration_seconds    INT NOT NULL DEFAULT 600,
    max_queue_size          INT NOT NULL DEFAULT 20,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_video_queue_settings_updated_at ON video_queue_settings;
CREATE TRIGGER trg_video_queue_settings_updated_at
    BEFORE UPDATE ON video_queue_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- Step 4: RLS
ALTER TABLE video_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE video_queue_settings ENABLE ROW LEVEL SECURITY;

-- Step 5: Grants
GRANT ALL ON video_queue TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE video_queue_id_seq TO anon, authenticated, service_role;
GRANT ALL ON video_queue_settings TO anon, authenticated, service_role;

-- Step 6: RLS Policies
DROP POLICY IF EXISTS "Allow authenticated read video_queue" ON video_queue;
CREATE POLICY "Allow authenticated read video_queue"
    ON video_queue FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Allow authenticated read video_queue_settings" ON video_queue_settings;
CREATE POLICY "Allow authenticated read video_queue_settings"
    ON video_queue_settings FOR SELECT TO authenticated USING (true);
