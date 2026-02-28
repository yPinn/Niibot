-- Migration 028: Add last_used_at to command_configs
-- Enables time-period filtering for top commands without session dependency.
-- Backfill existing rows that have been used (usage_count > 0) with NOW()
-- so time-period queries work immediately after migration.

ALTER TABLE command_configs ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ NULL;

UPDATE command_configs SET last_used_at = NOW() WHERE usage_count > 0;
