-- 006: Add command_configs and redemption_configs tables

-- 指令設定表（內建 + 自訂統一管理）
CREATE TABLE IF NOT EXISTS command_configs (
    id                 SERIAL PRIMARY KEY,
    channel_id         TEXT NOT NULL,
    command_name       TEXT NOT NULL,
    command_type       TEXT NOT NULL DEFAULT 'builtin' CHECK (command_type IN ('builtin', 'custom')),
    enabled            BOOLEAN DEFAULT TRUE,
    custom_response    TEXT,              -- NULL = 使用程式碼預設（僅部分指令支援）
    redirect_to        TEXT,              -- custom 類型用：目標指令+參數，如 "game valorant"
    cooldown_global    INT DEFAULT 0,     -- 全域冷卻秒數（0=無）
    cooldown_per_user  INT DEFAULT 0,     -- 每人冷卻秒數（0=無）
    min_role           TEXT DEFAULT 'everyone' CHECK (min_role IN ('everyone','subscriber','vip','moderator','broadcaster')),
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, command_name)
);

CREATE INDEX IF NOT EXISTS idx_command_configs_channel ON command_configs(channel_id);

-- 忠誠點數兌換設定表
CREATE TABLE IF NOT EXISTS redemption_configs (
    id               SERIAL PRIMARY KEY,
    channel_id       TEXT NOT NULL,
    action_type      TEXT NOT NULL CHECK (action_type IN ('vip', 'first', 'niibot_auth')),
    reward_name      TEXT NOT NULL,
    enabled          BOOLEAN DEFAULT TRUE,
    created_at       TIMESTAMPTZ DEFAULT NOW(),
    updated_at       TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel_id, action_type)
);

CREATE INDEX IF NOT EXISTS idx_redemption_configs_channel ON redemption_configs(channel_id);

-- Triggers（複用 fn_update_updated_at）
DROP TRIGGER IF EXISTS trg_command_configs_updated_at ON command_configs;
CREATE TRIGGER trg_command_configs_updated_at
    BEFORE UPDATE ON command_configs
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

DROP TRIGGER IF EXISTS trg_redemption_configs_updated_at ON redemption_configs;
CREATE TRIGGER trg_redemption_configs_updated_at
    BEFORE UPDATE ON redemption_configs
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- RLS
ALTER TABLE command_configs ENABLE ROW LEVEL SECURITY;
ALTER TABLE redemption_configs ENABLE ROW LEVEL SECURITY;

-- Grants（同 event_configs 模式）
GRANT ALL ON command_configs TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE command_configs_id_seq TO anon, authenticated, service_role;
GRANT ALL ON redemption_configs TO anon, authenticated, service_role;
GRANT USAGE, SELECT ON SEQUENCE redemption_configs_id_seq TO anon, authenticated, service_role;

-- RLS Policies
DROP POLICY IF EXISTS "Allow authenticated read command_configs" ON command_configs;
CREATE POLICY "Allow authenticated read command_configs"
    ON command_configs FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "Allow authenticated read redemption_configs" ON redemption_configs;
CREATE POLICY "Allow authenticated read redemption_configs"
    ON redemption_configs FOR SELECT TO authenticated USING (true);
