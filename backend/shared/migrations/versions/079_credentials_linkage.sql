-- 079: Bind tokens to identity rather than raw platform_user_id.
--
-- tokens.user_id today is platform_user_id (Twitch broadcaster_id), not users.id.
-- This couples credential lifetime to platform identity rather than to a stable
-- internal identity (problem when the same Twitch account ever needs to be
-- relinked to a different users row, or for the future Discord integration).
--
-- Add identity_id FK; backfill in migration 082. Keep user_id column intact for
-- now so existing repository code and the bot keep working during the rollout.

ALTER TABLE tokens
    ADD COLUMN IF NOT EXISTS identity_id UUID REFERENCES identities(id) ON DELETE CASCADE;

CREATE INDEX IF NOT EXISTS idx_tokens_identity_id
    ON tokens(identity_id)
    WHERE identity_id IS NOT NULL;
