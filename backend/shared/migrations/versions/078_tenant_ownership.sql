-- 078: Tenant ownership model.
--
-- channels represents a tenant (a broadcaster's workspace). This migration adds:
--   channels.owner_user_id    — the User who owns the tenant
--   channels.suspended_at     — tenant-level suspension (separate from membership suspension)
--   channels.suspended_reason — operator-facing reason
--   channel_members           — RBAC for who can manage the channel
--
-- channel_members.role values:
--   'owner'   — the broadcaster (implicit: granted at channel creation)
--   'manager' — invited collaborators (mods/editors) — schema-ready for future feature
--   'viewer'  — read-only access
--
-- Data backfill is in migration 081.

ALTER TABLE channels
    ADD COLUMN IF NOT EXISTS owner_user_id    UUID REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS suspended_at     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS suspended_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_channels_owner_user_id
    ON channels(owner_user_id)
    WHERE owner_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_channels_suspended
    ON channels(channel_id)
    WHERE suspended_at IS NOT NULL;

-- ============================================
-- channel_members — per-tenant RBAC
-- ============================================
CREATE TABLE IF NOT EXISTS channel_members (
    channel_id   TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id      UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role         TEXT NOT NULL
                 CHECK (role IN ('owner', 'manager', 'viewer')),
    granted_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    granted_by   UUID REFERENCES users(id) ON DELETE SET NULL,
    PRIMARY KEY (channel_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_channel_members_user_id
    ON channel_members(user_id);

-- Only one owner per channel. Guarded by partial UNIQUE so manager/viewer
-- rows aren't restricted.
CREATE UNIQUE INDEX IF NOT EXISTS uq_channel_members_one_owner
    ON channel_members(channel_id)
    WHERE role = 'owner';
