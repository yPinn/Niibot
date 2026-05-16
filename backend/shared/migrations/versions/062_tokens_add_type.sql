-- 060: Separate bot and broadcaster tokens for the same Twitch account.
--
-- Adds token_type column ('bot' | 'broadcaster') and changes PK to
-- (user_id, token_type) so the bot account can hold two independent tokens.
-- Existing rows default to 'broadcaster'.
-- After running this migration, re-run: python scripts/tw_oauth.py bot

ALTER TABLE tokens ADD COLUMN IF NOT EXISTS token_type TEXT NOT NULL DEFAULT 'broadcaster';

ALTER TABLE tokens DROP CONSTRAINT tokens_pkey;
ALTER TABLE tokens ADD PRIMARY KEY (user_id, token_type);
