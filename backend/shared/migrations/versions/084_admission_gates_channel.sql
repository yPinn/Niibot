-- 084: Admission state gates channel monitoring (channels.enabled).
--
-- ## Why
-- Before this migration, channels.enabled (whether the Twitch bot joins and
-- monitors a channel) was completely decoupled from memberships.status (the
-- admission source of truth). A brand-new, not-yet-approved user got a channel
-- row with enabled=TRUE at signup, so:
--   * the bot actually joined and operated in unapproved channels, and
--   * the admin "monitored channels" view mixed pending users in with active
--     tenants.
-- Admission review was effectively advisory.
--
-- ## Invariant enforced here
-- A channel may be enabled=TRUE (bot present) ONLY IF its owner's membership
-- is 'active'. Among active owners, enabled remains the owner's manual on/off
-- switch (defaults TRUE on the transition into 'active').
--
-- This is enforced with two triggers so the invariant survives the signup
-- ordering (the channel's owner_user_id is linked AFTER the membership row is
-- created). Together with the existing trg_channels_notify_toggle (which fires
-- pg_notify('channel_toggle') on every enabled change), the Twitch bot joins /
-- parts automatically — no application call sites to keep in sync.
--
-- Pattern matches the codebase's DB-as-enforcement approach (077 append-only
-- triggers, 083 RLS).

-- ============================================
-- 1. Default new channels to disabled.
--    Admission (below) is what turns a channel on.
-- ============================================
ALTER TABLE channels ALTER COLUMN enabled SET DEFAULT FALSE;

-- ============================================
-- 2. memberships.status transitions drive channels.enabled.
--    Fires the existing channel_toggle NOTIFY via the enabled change, so the
--    bot joins on approval and parts on reject/suspend in real time.
-- ============================================
CREATE OR REPLACE FUNCTION fn_sync_channel_enabled_from_membership()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_changed BOOLEAN;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_changed := TRUE;
    ELSE
        v_changed := NEW.status IS DISTINCT FROM OLD.status;
    END IF;

    IF v_changed THEN
        -- Owner may not be linked yet at INSERT time (signup links the channel
        -- owner AFTER the membership row is created); that case is a no-op here
        -- and handled by fn_channel_enabled_from_owner when the link is set.
        UPDATE channels
           SET enabled = (NEW.status = 'active')
         WHERE owner_user_id = NEW.user_id
           AND enabled IS DISTINCT FROM (NEW.status = 'active');
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_memberships_sync_channel_enabled ON memberships;
CREATE TRIGGER trg_memberships_sync_channel_enabled
    AFTER INSERT OR UPDATE OF status ON memberships
    FOR EACH ROW EXECUTE FUNCTION fn_sync_channel_enabled_from_membership();

-- ============================================
-- 3. Channels-side derive + guard, on every INSERT/UPDATE.
--
--    Two jobs:
--    a) DERIVE — when a channel's owner is first linked (or reassigned),
--       set enabled from that owner's membership. This is what enables the
--       owner's own channel at signup, where owner_user_id is linked AFTER the
--       membership row already exists (so the membership trigger above can't see
--       the channel yet). A re-auth that re-sets the SAME owner is not a change,
--       so it does NOT override an owner's manual disable.
--    b) GUARD — for any other write, a non-active owner can never set
--       enabled=TRUE. This closes the hole where a pending/suspended owner calls
--       the channel toggle endpoint directly (an enabled-only UPDATE that would
--       otherwise bypass the membership trigger). Active owners keep full manual
--       control of enabled (the guard only ever forces FALSE, never TRUE).
-- ============================================
CREATE OR REPLACE FUNCTION fn_channel_enabled_from_owner()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    v_owner_active BOOLEAN;
BEGIN
    IF NEW.owner_user_id IS NULL THEN
        -- Ownerless rows (e.g. the bot's own channel) are out of scope.
        RETURN NEW;
    END IF;

    v_owner_active := COALESCE(
        (SELECT status = 'active' FROM memberships WHERE user_id = NEW.owner_user_id),
        FALSE
    );

    IF TG_OP = 'INSERT' OR OLD.owner_user_id IS DISTINCT FROM NEW.owner_user_id THEN
        -- (a) owner (re)linked: derive enabled from membership.
        NEW.enabled := v_owner_active;
    ELSIF NEW.enabled AND NOT v_owner_active THEN
        -- (b) guard: non-active owner may not enable monitoring.
        NEW.enabled := FALSE;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_channels_enabled_from_owner ON channels;
CREATE TRIGGER trg_channels_enabled_from_owner
    BEFORE INSERT OR UPDATE ON channels
    FOR EACH ROW EXECUTE FUNCTION fn_channel_enabled_from_owner();

-- ============================================
-- 4. Backfill: disable any currently-enabled channel whose owner is not active.
--    "Not active" means the owner has no 'active' membership — covering
--    pending/suspended/rejected AND the defensive no-membership case. Using
--    NOT EXISTS(active) keeps this identical to fn_channel_enabled_from_owner's
--    guard instead of relying on the "every owner has a membership" invariant.
--    NULL-owner channels (e.g. the bot's own) are intentionally left untouched.
--    The enabled change fires channel_toggle, so a running bot parts these
--    channels immediately.
-- ============================================
UPDATE channels c
   SET enabled = FALSE
 WHERE c.enabled = TRUE
   AND c.owner_user_id IS NOT NULL
   AND NOT EXISTS (
       SELECT 1 FROM memberships m
        WHERE m.user_id = c.owner_user_id
          AND m.status = 'active'
   );
