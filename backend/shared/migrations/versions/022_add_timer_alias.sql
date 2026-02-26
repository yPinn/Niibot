-- Migration 022: Add command_alias to timers
-- Allows a timer to also be triggered manually via !alias in chat.
-- When triggered manually, the interval countdown resets (prevents double-posting).

ALTER TABLE timers ADD COLUMN IF NOT EXISTS command_alias TEXT;

-- Alias must be unique per channel (NULLs are excluded from uniqueness check)
CREATE UNIQUE INDEX IF NOT EXISTS timers_channel_alias_unique
    ON timers(channel_id, command_alias)
    WHERE command_alias IS NOT NULL;
