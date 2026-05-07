-- Persistent viewer channel status maintained via EventSub events.
-- All fields default to FALSE/NULL and are upserted incrementally.
CREATE TABLE viewer_channel_status (
    channel_id          TEXT        NOT NULL,
    user_id             TEXT        NOT NULL,
    username            TEXT        NOT NULL,
    display_name        TEXT,
    -- subscription
    is_subscribed       BOOLEAN     NOT NULL DEFAULT FALSE,
    sub_tier            TEXT,
    sub_gifted          BOOLEAN,
    sub_gifter          TEXT,
    -- roles
    is_mod              BOOLEAN     NOT NULL DEFAULT FALSE,
    is_vip              BOOLEAN     NOT NULL DEFAULT FALSE,
    -- ban
    is_banned           BOOLEAN     NOT NULL DEFAULT FALSE,
    ban_expires_at      TIMESTAMPTZ,
    ban_reason          TEXT,
    -- follow
    follow_since        TIMESTAMPTZ,
    -- profile cache (populated on first sheet open, refreshed on broadcaster_type change)
    profile_image_url   TEXT,
    offline_image_url   TEXT,
    account_created_at  TIMESTAMPTZ,
    broadcaster_type    TEXT,
    -- metadata
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel_id, user_id)
);

CREATE INDEX idx_viewer_channel_status_channel
    ON viewer_channel_status (channel_id);
