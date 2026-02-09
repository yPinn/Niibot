-- Migration 011: Fix cooldowns to match new defaults and cleanup redemptions
--
-- 010 ran before code changes, so some values were not updated.

-- 1. Force update all builtin cooldowns to new defaults
UPDATE command_configs SET cooldown = 5
WHERE command_name IN ('hi', 'help', 'uptime', 'rk', '運勢')
  AND command_type = 'builtin';

UPDATE command_configs SET cooldown = 15
WHERE command_name = 'ai'
  AND command_type = 'builtin';

-- 2. Delete all remaining 'redemptions' builtin commands
DELETE FROM command_configs
WHERE command_name = 'redemptions' AND command_type = 'builtin';
