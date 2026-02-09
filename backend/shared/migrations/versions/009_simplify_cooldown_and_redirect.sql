-- Migration 009: Simplify cooldown fields and merge redirect_to into custom_response
--
-- Changes:
-- 1. Merge redirect_to into custom_response (prefix with !)
-- 2. Remove redirect_to column
-- 3. Merge cooldown_global + cooldown_per_user into single cooldown column
-- 4. Merge channels default_cooldown_global + default_cooldown_per_user into default_cooldown

-- 1. Merge redirect_to → custom_response (! prefix = redirect)
UPDATE command_configs
SET custom_response = '!' || redirect_to
WHERE redirect_to IS NOT NULL AND custom_response IS NULL;

-- 2. Drop redirect_to column
ALTER TABLE command_configs DROP COLUMN IF EXISTS redirect_to;

-- 3. Merge cooldown columns into single 'cooldown'
ALTER TABLE command_configs ADD COLUMN IF NOT EXISTS cooldown INT;
UPDATE command_configs SET cooldown = GREATEST(cooldown_global, cooldown_per_user);
ALTER TABLE command_configs DROP COLUMN IF EXISTS cooldown_global;
ALTER TABLE command_configs DROP COLUMN IF EXISTS cooldown_per_user;

-- 4. Merge channel default cooldown columns
ALTER TABLE channels ADD COLUMN IF NOT EXISTS default_cooldown INT DEFAULT 0;
UPDATE channels SET default_cooldown = GREATEST(
    COALESCE(default_cooldown_global, 0),
    COALESCE(default_cooldown_per_user, 0)
);
ALTER TABLE channels DROP COLUMN IF EXISTS default_cooldown_global;
ALTER TABLE channels DROP COLUMN IF EXISTS default_cooldown_per_user;
