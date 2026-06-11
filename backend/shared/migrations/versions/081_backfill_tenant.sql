-- 081: Backfill channels.owner_user_id + channel_members(owner).
--
-- Channels currently use channel_id == Twitch broadcaster_id as PK, so the
-- owning user is whichever User has an identity row matching that platform_id.
--
-- Rules:
--   1. channels.owner_user_id  ← identities.user_id  WHERE
--                                 platform='twitch' AND platform_user_id=channel_id
--   2. channel_members(owner)  ← INSERT one row per channel with role='owner'
--   3. Orphan channels (no matching identity) keep owner_user_id NULL and emit
--      a NOTICE so operators can decide whether to clean them up.

-- ============================================
-- 1. channels.owner_user_id
-- ============================================
UPDATE channels c
SET owner_user_id = i.user_id
FROM identities i
WHERE i.platform = 'twitch'
  AND i.platform_user_id = c.channel_id
  AND c.owner_user_id IS NULL;

-- Surface orphans for operator visibility (no row data leaks; just count).
DO $$
DECLARE
    orphan_count INT;
BEGIN
    SELECT COUNT(*) INTO orphan_count FROM channels WHERE owner_user_id IS NULL;
    IF orphan_count > 0 THEN
        RAISE NOTICE 'Migration 081: % channels have no matching twitch identity (orphans)', orphan_count;
    END IF;
END $$;

-- ============================================
-- 2. channel_members — seed every owned channel with role='owner'
-- ============================================
INSERT INTO channel_members (channel_id, user_id, role, granted_at, granted_by)
SELECT
    c.channel_id,
    c.owner_user_id,
    'owner',
    COALESCE(c.created_at, NOW()),
    c.owner_user_id            -- granted_by = self for backfill provenance
FROM channels c
WHERE c.owner_user_id IS NOT NULL
ON CONFLICT (channel_id, user_id) DO NOTHING;
