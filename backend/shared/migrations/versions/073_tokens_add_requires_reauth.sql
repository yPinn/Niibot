-- Migration 073: Add requires_reauth flag to tokens table.
-- Set by the bot when a broadcaster token is invalid or missing required scopes.
-- Cleared automatically by upsert_token / upsert_token_only on re-authorization.
-- Checked by the API's /auth/user endpoint to force dashboard re-login.

ALTER TABLE tokens ADD COLUMN requires_reauth BOOLEAN NOT NULL DEFAULT FALSE;
