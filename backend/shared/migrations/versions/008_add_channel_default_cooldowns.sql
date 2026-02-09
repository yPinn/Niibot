-- channels 表加入預設冷卻欄位
ALTER TABLE channels ADD COLUMN IF NOT EXISTS default_cooldown_global INT DEFAULT 0;
ALTER TABLE channels ADD COLUMN IF NOT EXISTS default_cooldown_per_user INT DEFAULT 0;

-- command_configs 的冷卻欄位改為 nullable（NULL = 使用頻道預設）
ALTER TABLE command_configs ALTER COLUMN cooldown_global DROP DEFAULT;
ALTER TABLE command_configs ALTER COLUMN cooldown_per_user DROP DEFAULT;

-- 將現有的 0 值改為 NULL（代表使用預設）
UPDATE command_configs SET cooldown_global = NULL WHERE cooldown_global = 0;
UPDATE command_configs SET cooldown_per_user = NULL WHERE cooldown_per_user = 0;
