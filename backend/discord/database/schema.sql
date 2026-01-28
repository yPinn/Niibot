-- Birthday Feature Schema for Discord Bot
-- Run this script in Supabase SQL Editor to create the tables

-- Create updated_at trigger function if not exists
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- User birthday data (global)
CREATE TABLE IF NOT EXISTS birthdays (
    user_id BIGINT PRIMARY KEY,
    month SMALLINT NOT NULL,
    day SMALLINT NOT NULL,
    year SMALLINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT valid_month CHECK (month BETWEEN 1 AND 12),
    CONSTRAINT valid_day CHECK (day BETWEEN 1 AND 31),
    CONSTRAINT valid_year CHECK (year IS NULL OR year BETWEEN 1900 AND 2100)
);

-- Guild subscription relationships
CREATE TABLE IF NOT EXISTS birthday_subscriptions (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (guild_id, user_id),
    FOREIGN KEY (user_id) REFERENCES birthdays(user_id) ON DELETE CASCADE
);

-- Guild settings
CREATE TABLE IF NOT EXISTS birthday_settings (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    role_id BIGINT NOT NULL,
    message_template TEXT DEFAULT '今天是 {users} 的生日，請各位送上祝福！',
    last_notified_date DATE,
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_birthdays_month_day ON birthdays(month, day);
CREATE INDEX IF NOT EXISTS idx_subscriptions_guild ON birthday_subscriptions(guild_id);
CREATE INDEX IF NOT EXISTS idx_settings_enabled ON birthday_settings(enabled);

-- Triggers for updated_at
DROP TRIGGER IF EXISTS update_birthdays_updated_at ON birthdays;
CREATE TRIGGER update_birthdays_updated_at
    BEFORE UPDATE ON birthdays
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_birthday_settings_updated_at ON birthday_settings;
CREATE TRIGGER update_birthday_settings_updated_at
    BEFORE UPDATE ON birthday_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
