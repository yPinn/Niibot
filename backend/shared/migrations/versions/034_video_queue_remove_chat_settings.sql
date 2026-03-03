-- Migration 034: CLI !vq is now mod-only; regular users can only query (list/np).
-- Removes chat-source-specific columns that are no longer needed.
ALTER TABLE video_queue_settings DROP COLUMN IF EXISTS chat_enabled;
ALTER TABLE video_queue_settings DROP COLUMN IF EXISTS min_role_chat;
ALTER TABLE video_queue_settings DROP COLUMN IF EXISTS max_duration_seconds;
