-- 015: Add game queue tables for channel points game queue feature

-- Step 1: Extend redemption_configs CHECK constraint to include 'game_queue'
ALTER TABLE redemption_configs
    DROP CONSTRAINT IF EXISTS redemption_configs_action_type_check;
ALTER TABLE redemption_configs
    ADD CONSTRAINT redemption_configs_action_type_check
    CHECK (action_type IN ('vip', 'first', 'niibot_auth', 'game_queue'));

-- Step 2: Game queue entries table (FIFO queue)
CREATE TABLE IF NOT EXISTS game_queue_entries (
    id              BIGSERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    user_id         TEXT NOT NULL,
    user_name       TEXT NOT NULL,
    redeemed_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    removed_at      TIMESTAMPTZ,
    removal_reason  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One active entry per user per channel
CREATE UNIQUE INDEX IF NOT EXISTS idx_game_queue_one_active_per_user
    ON game_queue_entries(channel_id, user_id) WHERE removed_at IS NULL;

-- Fast lookup for active entries ordered by redeemed_at
CREATE INDEX IF NOT EXISTS idx_game_queue_entries_active
    ON game_queue_entries(channel_id, redeemed_at) WHERE removed_at IS NULL;

-- Step 3: Game queue settings table
CREATE TABLE IF NOT EXISTS game_queue_settings (
    id              SERIAL PRIMARY KEY,
    channel_id      TEXT NOT NULL UNIQUE,
    group_size      INT NOT NULL DEFAULT 4 CHECK (group_size > 0 AND group_size <= 20),
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_game_queue_settings_updated_at ON game_queue_settings;
CREATE TRIGGER trg_game_queue_settings_updated_at
    BEFORE UPDATE ON game_queue_settings
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

