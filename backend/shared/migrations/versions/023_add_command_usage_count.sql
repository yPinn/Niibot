-- Migration 023: Add usage_count to command_configs
-- Tracks all-time command usage regardless of stream session status.
-- Previously, command usage was only counted via command_stats (session-gated).

ALTER TABLE command_configs ADD COLUMN IF NOT EXISTS usage_count INT NOT NULL DEFAULT 0;
