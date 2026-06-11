-- 082: Backfill tokens.identity_id from existing tokens.user_id (= twitch broadcaster_id).
--
-- tokens hold both 'broadcaster' and 'bot' rows. For each row, look up the
-- matching identity by (platform='twitch', platform_user_id=tokens.user_id).
-- Rows without a matching identity (e.g. the bot account's token row when no
-- corresponding User exists) keep identity_id NULL. Future code reads can
-- handle NULL as "legacy unbound".

UPDATE tokens t
SET identity_id = i.id
FROM identities i
WHERE i.platform = 'twitch'
  AND i.platform_user_id = t.user_id
  AND t.identity_id IS NULL;

DO $$
DECLARE
    unbound_count INT;
BEGIN
    SELECT COUNT(*) INTO unbound_count FROM tokens WHERE identity_id IS NULL;
    IF unbound_count > 0 THEN
        RAISE NOTICE 'Migration 082: % token rows have no matching identity (likely bot account)', unbound_count;
    END IF;
END $$;
