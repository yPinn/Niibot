-- Migration 029: Add announce flag to timers
-- When enabled, the timer fires via /announce instead of a regular chat message.

ALTER TABLE timers ADD COLUMN announce BOOLEAN NOT NULL DEFAULT FALSE;
