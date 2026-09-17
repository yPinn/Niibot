-- Manual collab-marking + conversion attribution for Matcher.
-- matcher_collab_targets freezes the exclusive-to-partner audience at mark
-- time so later channel_overlap_viewers refreshes can't retroactively change
-- who counts as "converted" for a past collab.

CREATE TABLE matcher_collab_events (
    id                  SERIAL PRIMARY KEY,
    home_channel_id     TEXT NOT NULL,
    partner_channel_id  TEXT NOT NULL,
    window_days         SMALLINT NOT NULL,
    occurred_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    note                TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_collab_events_home_partner
    ON matcher_collab_events (home_channel_id, partner_channel_id, occurred_at DESC);

CREATE TABLE matcher_collab_targets (
    collab_id  INT  NOT NULL REFERENCES matcher_collab_events(id) ON DELETE CASCADE,
    user_id    TEXT NOT NULL,
    username   TEXT NOT NULL,
    PRIMARY KEY (collab_id, user_id)
);
