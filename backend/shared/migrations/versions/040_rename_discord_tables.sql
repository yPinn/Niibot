-- Rename birthday tables to use discord_ prefix for clear domain separation.
-- Foreign key references by OID are unaffected by table renames.
-- Triggers and indexes follow the renamed tables automatically.

ALTER TABLE birthdays RENAME TO discord_birthdays;
ALTER TABLE birthday_subscriptions RENAME TO discord_birthday_subscriptions;
ALTER TABLE birthday_settings RENAME TO discord_birthday_settings;

-- Update constraint names for consistency
ALTER TABLE discord_birthday_subscriptions
    RENAME CONSTRAINT birthday_subscriptions_pkey TO discord_birthday_subscriptions_pkey;
ALTER TABLE discord_birthday_subscriptions
    RENAME CONSTRAINT birthday_subscriptions_user_id_fkey TO discord_birthday_subscriptions_user_id_fkey;
ALTER TABLE discord_birthday_settings
    RENAME CONSTRAINT birthday_settings_pkey TO discord_birthday_settings_pkey;
