-- PostgreSQL/Supabase Database Initialization Script for TwitchIO Bot
-- This script creates the necessary tables for storing Twitch OAuth tokens and channels

-- Create tokens table
-- Stores OAuth tokens for authenticated users (bot and channel owners)
CREATE TABLE IF NOT EXISTS tokens (
    user_id TEXT PRIMARY KEY,  -- Twitch user_id (numeric string, e.g. "123456789")
    token TEXT NOT NULL,        -- OAuth access token
    refresh TEXT NOT NULL,      -- OAuth refresh token
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create channels table for multi-channel support
-- Note: In Twitch, a channel IS a user. channel_id == broadcaster_user_id == user_id
CREATE TABLE IF NOT EXISTS channels (
    channel_id TEXT PRIMARY KEY,      -- Twitch user_id of the channel owner (broadcaster_user_id)
    channel_name TEXT NOT NULL UNIQUE, -- Lowercase Twitch username (e.g. "streamer_name")
    enabled BOOLEAN DEFAULT true,      -- Whether bot is active in this channel
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on channel_name for faster lookups
CREATE INDEX IF NOT EXISTS idx_channels_name ON channels(channel_name);
CREATE INDEX IF NOT EXISTS idx_channels_enabled ON channels(enabled);

-- Create a trigger to automatically update the updated_at column
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tokens_updated_at BEFORE UPDATE ON tokens
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_channels_updated_at BEFORE UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
