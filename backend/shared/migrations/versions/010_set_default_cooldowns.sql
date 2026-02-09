-- Migration 010: Set proper default cooldowns for all commands
--
-- Changes:
-- 1. Update channel default_cooldown from 0 to 5
-- 2. Set cooldown for all builtin commands (5s default, 15s for ai)
-- 3. Delete orphaned 'redemptions' command configs

-- 1. Channel default cooldown: 0 → 5
UPDATE channels SET default_cooldown = 5 WHERE default_cooldown = 0;
ALTER TABLE channels ALTER COLUMN default_cooldown SET DEFAULT 5;

-- 2. Builtin command cooldowns (only update where cooldown IS NULL or 0)
UPDATE command_configs SET cooldown = 5
WHERE command_name IN ('hi', 'help', 'uptime', '運勢', 'rk')
  AND command_type = 'builtin'
  AND (cooldown IS NULL OR cooldown = 0);

UPDATE command_configs SET cooldown = 15
WHERE command_name = 'ai'
  AND command_type = 'builtin'
  AND (cooldown IS NULL OR cooldown = 0);

-- 3. Remove orphaned 'redemptions' builtin command
DELETE FROM command_configs
WHERE command_name = 'redemptions' AND command_type = 'builtin';
