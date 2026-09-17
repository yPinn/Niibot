-- Multi-window support for Matcher's potential-viewer detail.
-- channel_overlap_summary already keys on window_days; channel_overlap_viewers
-- did not, so every refresh_overlap(days=X) call silently overwrote viewer
-- rows regardless of which window they belonged to.

ALTER TABLE channel_overlap_viewers
    ADD COLUMN IF NOT EXISTS window_days SMALLINT NOT NULL DEFAULT 30;

ALTER TABLE channel_overlap_viewers
    DROP CONSTRAINT IF EXISTS channel_overlap_viewers_pkey;

ALTER TABLE channel_overlap_viewers
    ADD PRIMARY KEY (home_channel_id, partner_channel_id, user_id, window_days);

DROP INDEX IF EXISTS idx_overlap_viewers_score;

CREATE INDEX idx_overlap_viewers_score
    ON channel_overlap_viewers (home_channel_id, window_days, potential_score DESC);
