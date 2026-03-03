-- Migration 033: Add per-source max duration for redemption
--
-- Principle: those who spend money (redemption > chat) can queue longer videos.
-- Dashboard and donation sources are always unrestricted.
--
--   chat       → max_duration_seconds      (existing, default 600s / 10 min)
--   redemption → max_duration_redemption   (new,      default 1200s / 20 min)
--   donation   → no limit (real money; enforced at application layer)
--   dashboard  → no limit (broadcaster authority; already bypassed in router)

ALTER TABLE video_queue_settings
    ADD COLUMN IF NOT EXISTS max_duration_redemption INT NOT NULL DEFAULT 1200;
