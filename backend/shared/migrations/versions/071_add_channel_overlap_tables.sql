CREATE TABLE channel_overlap_summary (
    home_channel_id         TEXT         NOT NULL,
    partner_channel_id      TEXT         NOT NULL,
    window_days             SMALLINT     NOT NULL DEFAULT 30,
    partner_unique_chatters INT          NOT NULL DEFAULT 0,
    home_unique_chatters    INT          NOT NULL DEFAULT 0,
    shared_chatters         INT          NOT NULL DEFAULT 0,
    exclusive_to_partner    INT          NOT NULL DEFAULT 0,
    overlap_pct             NUMERIC(5,2) NOT NULL DEFAULT 0,
    computed_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (home_channel_id, partner_channel_id, window_days)
);

CREATE TABLE channel_overlap_viewers (
    home_channel_id     TEXT         NOT NULL,
    partner_channel_id  TEXT         NOT NULL,
    user_id             TEXT         NOT NULL,
    username            TEXT         NOT NULL,
    display_name        TEXT,
    partner_sessions    SMALLINT     NOT NULL DEFAULT 0,
    partner_messages    INT          NOT NULL DEFAULT 0,
    partner_watch_sec   INT          NOT NULL DEFAULT 0,
    partner_last_seen   TIMESTAMPTZ,
    home_sessions       SMALLINT     NOT NULL DEFAULT 0,
    home_messages       INT          NOT NULL DEFAULT 0,
    potential_score     NUMERIC(8,2) NOT NULL DEFAULT 0,
    computed_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    PRIMARY KEY (home_channel_id, partner_channel_id, user_id)
);

CREATE INDEX idx_overlap_viewers_score
    ON channel_overlap_viewers(home_channel_id, potential_score DESC);
