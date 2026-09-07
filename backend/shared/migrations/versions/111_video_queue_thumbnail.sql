-- Store the poster/cover image URL for a queued video so the dashboard "now
-- playing" / "up next" cards can show a real thumbnail instead of a placeholder.
--
-- Filled at INSERT from the metadata fetch (YouTube snippet.thumbnails, Twitch
-- Helix thumbnail_url, Bilibili `pic`); never UPDATEd, so it is not added to the
-- notify-on-update trigger's column list (migration 106). Nullable — Bilibili
-- risk control or any fetch failure just leaves it empty and the card falls
-- back to the placeholder.

ALTER TABLE video_queue ADD COLUMN IF NOT EXISTS thumbnail_url TEXT;
