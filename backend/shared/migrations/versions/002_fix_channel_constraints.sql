-- Fix empty channel_name values and add UNIQUE constraint
-- Background: some channels were created via OAuth with empty username,
-- sync_empty_names() fills them later from Twitch API.

-- Step 1: Set empty channel_name to channel_id as placeholder
UPDATE channels
SET channel_name = channel_id, updated_at = NOW()
WHERE channel_name IS NULL OR channel_name = '';

-- Step 2: Add UNIQUE constraint (safe now that duplicates are resolved)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_channels_channel_name'
    ) THEN
        ALTER TABLE channels
        ADD CONSTRAINT uq_channels_channel_name UNIQUE (channel_name);
    END IF;
END $$;

-- Step 3: Rename legacy triggers/functions to new convention (idempotent)
-- Old: update_tokens_updated_at        → trg_tokens_updated_at
-- Old: update_channels_updated_at      → trg_channels_updated_at
-- Old: channel_toggle_trigger          → trg_channels_notify_toggle
-- Old: update_discord_users_updated_at → trg_discord_users_updated_at
-- Old: update_birthdays_updated_at     → trg_birthdays_updated_at
-- Old: update_birthday_settings_updated_at → trg_birthday_settings_updated_at
-- Old: update_updated_at_column()      → fn_update_updated_at()
-- Old: notify_channel_toggle()         → fn_notify_channel_toggle()

-- Drop old triggers (new ones are created in 000_initial_schema)
DROP TRIGGER IF EXISTS update_tokens_updated_at ON tokens;
DROP TRIGGER IF EXISTS update_channels_updated_at ON channels;
DROP TRIGGER IF EXISTS channel_toggle_trigger ON channels;
DROP TRIGGER IF EXISTS update_discord_users_updated_at ON discord_users;
DROP TRIGGER IF EXISTS update_birthdays_updated_at ON birthdays;
DROP TRIGGER IF EXISTS update_birthday_settings_updated_at ON birthday_settings;

-- Drop old functions (only if new ones exist)
DROP FUNCTION IF EXISTS update_updated_at_column() CASCADE;
DROP FUNCTION IF EXISTS notify_channel_toggle() CASCADE;
