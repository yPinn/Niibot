-- Migration 043: Add requested_by_id column to video_queue
-- Stores the Twitch user ID of the requester alongside the display name.
-- Per-user limits and cooldown checks will use user_id when available,
-- making them resilient to username changes.

ALTER TABLE video_queue
    ADD COLUMN requested_by_id TEXT;
