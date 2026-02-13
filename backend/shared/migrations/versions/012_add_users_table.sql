-- ============================================
-- 012: Add unified users table + linked accounts
-- ============================================

-- users 表：統一身份 + 偏好
CREATE TABLE IF NOT EXISTS users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name TEXT,
    avatar       TEXT,
    theme        TEXT NOT NULL DEFAULT 'system'
                 CHECK (theme IN ('dark', 'light', 'system')),
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    updated_at   TIMESTAMPTZ DEFAULT NOW()
);

DROP TRIGGER IF EXISTS trg_users_updated_at ON users;
CREATE TRIGGER trg_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- 平台帳號連結
CREATE TABLE IF NOT EXISTS user_linked_accounts (
    user_id          UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform         TEXT NOT NULL CHECK (platform IN ('twitch', 'discord')),
    platform_user_id TEXT NOT NULL,
    username         TEXT,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (platform, platform_user_id),
    UNIQUE (user_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_linked_user_id ON user_linked_accounts(user_id);
