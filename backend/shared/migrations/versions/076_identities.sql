-- 076: Promote user_linked_accounts -> identities (stable platform identity layer).
--
-- Adds:
--   id           UUID PRIMARY KEY (so credentials / events can FK to a stable identity row)
--   linked_at    TIMESTAMPTZ (kept distinct from created_at semantics)
--   last_seen_at TIMESTAMPTZ (touched on every OAuth callback / token refresh)
--
-- Preserves existing UNIQUE (platform, platform_user_id) and (user_id, platform)
-- constraints, so cross-row invariants are unchanged.
--
-- The table is RENAMED to `identities`. Backwards-compat view `user_linked_accounts`
-- is created so any legacy code paths that have not been migrated keep working
-- during the rollout window. Drop the view in a follow-up migration once all
-- repositories have been switched.

-- 1. Add new columns BEFORE rename so existing rows pick up defaults.
ALTER TABLE user_linked_accounts
    ADD COLUMN IF NOT EXISTS id           UUID NOT NULL DEFAULT gen_random_uuid(),
    ADD COLUMN IF NOT EXISTS linked_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Backfill linked_at + last_seen_at from the existing created_at column where
-- present. This migration runs once per DB, so it's safe to overwrite the
-- freshly-defaulted NOW() values with the original signup time.
UPDATE user_linked_accounts
SET linked_at    = created_at,
    last_seen_at = created_at
WHERE created_at IS NOT NULL;

-- 2. Ensure `id` is unique so it can act as a logical identity key.
CREATE UNIQUE INDEX IF NOT EXISTS uq_user_linked_accounts_id
    ON user_linked_accounts(id);

-- 3. Rename table -> identities. Old (platform, platform_user_id) PK is preserved.
ALTER TABLE user_linked_accounts RENAME TO identities;

-- Rename associated indexes for clarity (best-effort; ignored if not present).
ALTER INDEX IF EXISTS idx_linked_user_id           RENAME TO idx_identities_user_id;
ALTER INDEX IF EXISTS uq_user_linked_accounts_id   RENAME TO uq_identities_id;
ALTER INDEX IF EXISTS user_linked_accounts_pkey    RENAME TO identities_pkey;
ALTER INDEX IF EXISTS user_linked_accounts_user_id_platform_key
                                                  RENAME TO identities_user_id_platform_key;

-- 4. Backwards-compat view so any not-yet-migrated reader keeps working.
--    Writes still go to the real table via repositories; this view is read-only.
CREATE OR REPLACE VIEW user_linked_accounts AS
SELECT user_id, platform, platform_user_id, username, created_at
FROM identities;
