-- 080: Backfill admission data from legacy tables.
--
-- Source tables (still present, untouched):
--   users.is_activated         — boolean admission flag
--   activation_requests        — pending/approved/rejected request rows
--   activation_codes           — historic OTP redemptions
--
-- Target tables:
--   memberships                — current admission state per user
--   membership_events          — append-only audit log derived from history
--
-- Rules:
--   1. Every users row gets exactly one memberships row.
--   2. memberships.status is derived in this priority:
--        suspended_at IS NOT NULL on the channel → 'suspended' (skipped — no
--                                                  suspension field exists yet
--                                                  in legacy data)
--        is_activated = TRUE                     → 'active'
--        most recent activation_requests.status='rejected' (and no later
--          pending) → 'rejected'
--        otherwise                               → 'pending'
--
--   3. membership_events is reconstructed in chronological order:
--        For each activation_requests row:
--          INSERT (event_type='requested', actor='system', occurred_at=created_at)
--          IF reviewed_at IS NOT NULL AND status IN ('approved','rejected'):
--            INSERT (event_type=status,    actor='owner',  occurred_at=reviewed_at)
--        For each activation_codes row with used_at IS NOT NULL:
--          INSERT (event_type='approved', actor='system',
--                  reason='otp_redeem',  occurred_at=used_at,
--                  metadata={'code_hash': ...})
--        For users whose activation has NO matching request or OTP history
--          but is_activated=TRUE (e.g. the owner, or pre-activation_codes era):
--          INSERT (event_type='auto_admitted', actor='system',
--                  reason='legacy_backfill', occurred_at=users.updated_at)

-- ============================================
-- 1. memberships — one row per user
-- ============================================
INSERT INTO memberships (user_id, status, granted_at, reason, updated_at)
SELECT
    u.id,
    CASE
        WHEN u.is_activated THEN 'active'
        WHEN EXISTS (
            SELECT 1 FROM activation_requests ar
            WHERE ar.user_id = u.id
              AND ar.status = 'rejected'
              AND NOT EXISTS (
                  SELECT 1 FROM activation_requests ar2
                  WHERE ar2.user_id = u.id
                    AND ar2.status = 'pending'
                    AND ar2.created_at > ar.created_at
              )
        ) THEN 'rejected'
        ELSE 'pending'
    END AS status,
    CASE WHEN u.is_activated THEN COALESCE(u.updated_at, NOW()) ELSE NULL END AS granted_at,
    CASE WHEN u.is_activated THEN 'legacy_backfill' ELSE NULL END AS reason,
    COALESCE(u.updated_at, NOW())
FROM users u
ON CONFLICT (user_id) DO NOTHING;

-- ============================================
-- 2. membership_events — replay request history
-- ============================================

-- 2a. Every activation_request becomes a 'requested' event.
-- actor_type='system' because legacy requests were created automatically by
-- the OAuth callback's slow path, NOT by an explicit user action — that
-- coupling is precisely what the new admission model removes. note is
-- preserved as the reason so the original message (if any) survives.
INSERT INTO membership_events
    (user_id, event_type, actor_type, reason, metadata, occurred_at)
SELECT
    ar.user_id,
    'requested',
    'system',
    COALESCE(NULLIF(ar.note, ''), 'legacy_oauth_signup'),
    jsonb_build_object(
        'platform', ar.platform,
        'platform_user_id', ar.platform_user_id,
        'legacy_request_id', ar.id
    ),
    ar.created_at
FROM activation_requests ar;

-- 2b. Reviewed requests become approved/rejected events.
INSERT INTO membership_events
    (user_id, event_type, actor_type, reason, metadata, occurred_at)
SELECT
    ar.user_id,
    ar.status,
    'owner',
    NULL,
    jsonb_build_object(
        'platform', ar.platform,
        'platform_user_id', ar.platform_user_id,
        'legacy_request_id', ar.id
    ),
    ar.reviewed_at
FROM activation_requests ar
WHERE ar.reviewed_at IS NOT NULL
  AND ar.status IN ('approved', 'rejected');

-- 2c. Redeemed activation_codes become system-attributed 'approved' events.
INSERT INTO membership_events
    (user_id, event_type, actor_type, reason, metadata, occurred_at)
SELECT
    ac.used_by_user_id,
    'approved',
    'system',
    'otp_redeem',
    jsonb_build_object(
        'platform', ac.platform,
        'platform_user_id', ac.platform_user_id,
        'code_hash', ac.code_hash
    ),
    ac.used_at
FROM activation_codes ac
WHERE ac.used_at IS NOT NULL
  AND ac.used_by_user_id IS NOT NULL;

-- 2d. Activated users with no matching history get a synthetic auto_admitted event.
--     Common case: the owner (activated in OAuth callback bypass) and users
--     migrated from before activation_requests existed.
INSERT INTO membership_events
    (user_id, event_type, actor_type, reason, metadata, occurred_at)
SELECT
    u.id,
    'auto_admitted',
    'system',
    'legacy_backfill',
    '{}'::jsonb,
    COALESCE(u.updated_at, u.created_at, NOW())
FROM users u
WHERE u.is_activated = TRUE
  AND NOT EXISTS (
      SELECT 1 FROM membership_events me
      WHERE me.user_id = u.id
        AND me.event_type IN ('approved', 'auto_admitted')
  );
