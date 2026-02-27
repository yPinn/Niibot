-- Migration 024: Add aliases column to message_triggers
-- Allows a single trigger to match multiple patterns (comma-separated, like command aliases).

ALTER TABLE message_triggers ADD COLUMN IF NOT EXISTS aliases TEXT;

COMMENT ON COLUMN message_triggers.aliases IS
    'Comma-separated alternative patterns. Any match fires the trigger response.';
