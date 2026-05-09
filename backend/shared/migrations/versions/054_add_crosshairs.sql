-- 054: Add crosshairs table for per-channel crosshair code repository

CREATE TABLE IF NOT EXISTS crosshairs (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    channel_id    TEXT        NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    game          TEXT        NOT NULL CHECK (game IN ('valorant')),
    name          TEXT        NOT NULL,
    code          TEXT        NOT NULL,
    description   TEXT,
    display_order INT         NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_crosshairs_channel_id
    ON crosshairs(channel_id);

DROP TRIGGER IF EXISTS trg_crosshairs_updated_at ON crosshairs;
CREATE TRIGGER trg_crosshairs_updated_at
    BEFORE UPDATE ON crosshairs
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();
