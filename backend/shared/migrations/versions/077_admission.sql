-- 077: Admission + auth audit model.
--
-- Replaces:
--   users.is_activated       -> memberships.status (state machine)
--   activation_requests      -> memberships + membership_events (append-only audit)
--
-- New tables:
--   memberships          — current admission state, 1:1 with users
--   membership_events    — append-only audit log of all admission decisions
--   auth_events          — login / reauth / scope upgrade audit
--
-- This migration only creates structure. Data backfill happens in 080.
-- users.is_activated and activation_requests are KEPT during the rollout for
-- dual-read / rollback safety; they are dropped in a later migration.

-- ============================================
-- memberships — current admission state
-- ============================================
CREATE TABLE IF NOT EXISTS memberships (
    user_id     UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    status      TEXT NOT NULL
                CHECK (status IN ('pending', 'active', 'suspended', 'rejected')),
    granted_at  TIMESTAMPTZ,
    granted_by  UUID REFERENCES users(id) ON DELETE SET NULL,
    reason      TEXT,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memberships_status
    ON memberships(status)
    WHERE status IN ('pending', 'suspended');  -- partial: hot queries are pending/suspended

DROP TRIGGER IF EXISTS trg_memberships_updated_at ON memberships;
CREATE TRIGGER trg_memberships_updated_at
    BEFORE UPDATE ON memberships
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- ============================================
-- membership_events — append-only audit log
-- ============================================
CREATE TABLE IF NOT EXISTS membership_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type      TEXT NOT NULL
                    CHECK (event_type IN (
                        'requested',
                        'auto_admitted',
                        'approved',
                        'rejected',
                        'suspended',
                        'reinstated',
                        'withdrawn'
                    )),
    actor_type      TEXT NOT NULL
                    CHECK (actor_type IN ('system', 'owner', 'user')),
    actor_user_id   UUID REFERENCES users(id) ON DELETE SET NULL,
    reason          TEXT,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_membership_events_user_time
    ON membership_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_membership_events_type_time
    ON membership_events(event_type, occurred_at DESC);

-- Enforce append-only at DB level. UPDATE / DELETE are blocked via a trigger
-- so application-layer bugs cannot rewrite history.
CREATE OR REPLACE FUNCTION fn_membership_events_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'membership_events is append-only (no % allowed)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_membership_events_no_update ON membership_events;
CREATE TRIGGER trg_membership_events_no_update
    BEFORE UPDATE OR DELETE ON membership_events
    FOR EACH ROW EXECUTE FUNCTION fn_membership_events_immutable();

-- ============================================
-- auth_events — login / reauth / scope upgrade audit
-- ============================================
CREATE TABLE IF NOT EXISTS auth_events (
    id            BIGSERIAL PRIMARY KEY,
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    identity_id   UUID REFERENCES identities(id) ON DELETE SET NULL,
    event_type    TEXT NOT NULL
                  CHECK (event_type IN (
                      'login',
                      'reauth',
                      'logout',
                      'scope_upgrade',
                      'reauth_required',
                      'reconciled'           -- identity row recovered via reconciliation
                  )),
    metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_auth_events_user_time
    ON auth_events(user_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_auth_events_identity_time
    ON auth_events(identity_id, occurred_at DESC)
    WHERE identity_id IS NOT NULL;

-- Same immutability guarantee for auth_events.
DROP TRIGGER IF EXISTS trg_auth_events_no_update ON auth_events;
CREATE TRIGGER trg_auth_events_no_update
    BEFORE UPDATE OR DELETE ON auth_events
    FOR EACH ROW EXECUTE FUNCTION fn_membership_events_immutable();
