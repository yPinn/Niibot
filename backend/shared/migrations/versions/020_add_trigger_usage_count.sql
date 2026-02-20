-- Migration 020: Add usage_count to message_triggers

ALTER TABLE message_triggers ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0;
