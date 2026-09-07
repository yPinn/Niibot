-- 110: per-channel Video Queue blocklist.
--
-- One row = one rule. `kind` says what `value` matches against a submission,
-- checked on all three add paths (chat, channel-points redemption, dashboard)
-- before the entry is inserted:
--
--   video    — exact video_id (platform-native id, as stored on video_queue)
--   creator  — exact creator id (not populated yet; see B3 — the metadata
--              plumbing for creator_id lands separately, the CHECK allows it now
--              so that PR needs no migration)
--   keyword  — case-insensitive substring of the video title
--   user     — the requester, matched on requested_by_id first, else the
--              lowercased requested_by login
--
-- `label` is a human note shown in the dashboard list (e.g. the video/creator
-- title captured at block time); `value` is what actually gets matched.

CREATE TABLE video_queue_blocklist (
    id          BIGSERIAL PRIMARY KEY,
    channel_id  TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    kind        TEXT NOT NULL CHECK (kind IN ('video', 'creator', 'keyword', 'user')),
    value       TEXT NOT NULL CHECK (char_length(value) BETWEEN 1 AND 256),
    label       TEXT CHECK (label IS NULL OR char_length(label) <= 256),
    created_by  TEXT CHECK (created_by IS NULL OR char_length(created_by) <= 128),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- One rule per (channel, kind, value); matching is case-insensitive so the
-- uniqueness key is too — blocking "LoFi" and "lofi" is the same rule.
CREATE UNIQUE INDEX idx_video_queue_blocklist_unique
    ON video_queue_blocklist (channel_id, kind, lower(value));

CREATE INDEX idx_video_queue_blocklist_channel
    ON video_queue_blocklist (channel_id, kind);
