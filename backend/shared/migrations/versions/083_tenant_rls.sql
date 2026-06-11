-- 083: Postgres Row-Level Security policies for tenant isolation.
--
-- ## Why
-- The application layer already filters every channel-scoped query by
-- caller's channel_id. RLS is the SECOND line of defence: even if a router
-- forgets to filter (or a future endpoint is added without going through
-- require_tenant_access), the database will refuse to return rows from other
-- tenants.
--
-- ## How it works
-- A session-local GUC `app.current_channel_id` is set by the API layer at
-- the start of each request (see TenantService.bind_session). Policies
-- match rows where channel_id = current_setting(...). When the GUC is unset
-- (background jobs, admin queries), policies are bypassed by the SUPERUSER
-- or by an explicit BYPASSRLS role attribute on the bot DB user.
--
-- ## Rollout safety
-- The policies are CREATED in this migration but ROW LEVEL SECURITY is
-- LEFT DISABLED. Operators flip it on per-table in a follow-up after a
-- shakedown window. To enable for, e.g., commands:
--
--     ALTER TABLE commands ENABLE ROW LEVEL SECURITY;
--
-- ## Tables in scope
-- All tables that already carry a channel_id column. Adding a new table
-- with channel_id should append a matching policy here.

-- Reusable predicate. NULL-safe: when the GUC is unset, current_setting
-- returns NULL (the missing_ok=true form), which makes every comparison
-- false, so RLS-enabled tables become invisible to that session. Bot's
-- DB role must be granted BYPASSRLS for background jobs.
CREATE OR REPLACE FUNCTION fn_tenant_match(row_channel_id TEXT)
RETURNS BOOLEAN
LANGUAGE sql
STABLE
AS $$
    SELECT row_channel_id = current_setting('app.current_channel_id', true)
$$;

-- Helper macro pattern (Postgres has no macros — written inline per table).

-- ============================================
-- commands (command_configs in actual code)
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'command_configs') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_command_configs_tenant ON command_configs';
        EXECUTE 'CREATE POLICY p_command_configs_tenant ON command_configs
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- crosshairs
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'crosshairs') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_crosshairs_tenant ON crosshairs';
        EXECUTE 'CREATE POLICY p_crosshairs_tenant ON crosshairs
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- timers
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'timers') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_timers_tenant ON timers';
        EXECUTE 'CREATE POLICY p_timers_tenant ON timers
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- message_triggers
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'message_triggers') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_message_triggers_tenant ON message_triggers';
        EXECUTE 'CREATE POLICY p_message_triggers_tenant ON message_triggers
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- game_queue
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'game_queue') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_game_queue_tenant ON game_queue';
        EXECUTE 'CREATE POLICY p_game_queue_tenant ON game_queue
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- video_queue
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'video_queue') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_video_queue_tenant ON video_queue';
        EXECUTE 'CREATE POLICY p_video_queue_tenant ON video_queue
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- ai_settings
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'ai_settings') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_ai_settings_tenant ON ai_settings';
        EXECUTE 'CREATE POLICY p_ai_settings_tenant ON ai_settings
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- ============================================
-- event_configs / redemption_configs (if present)
-- ============================================
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'event_configs') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_event_configs_tenant ON event_configs';
        EXECUTE 'CREATE POLICY p_event_configs_tenant ON event_configs
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'redemption_configs') THEN
        EXECUTE 'DROP POLICY IF EXISTS p_redemption_configs_tenant ON redemption_configs';
        EXECUTE 'CREATE POLICY p_redemption_configs_tenant ON redemption_configs
                 USING (fn_tenant_match(channel_id))
                 WITH CHECK (fn_tenant_match(channel_id))';
    END IF;
END $$;

-- NOTE: ROW LEVEL SECURITY is intentionally NOT enabled here. To enable per
-- table during rollout (after the application layer is fully wired to
-- TenantService.bind_session):
--
--   ALTER TABLE command_configs   ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE crosshairs        ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE timers            ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE message_triggers  ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE game_queue        ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE video_queue       ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE ai_settings       ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE event_configs     ENABLE ROW LEVEL SECURITY;
--   ALTER TABLE redemption_configs ENABLE ROW LEVEL SECURITY;
--
-- And grant the bot's background-job role BYPASSRLS:
--   ALTER ROLE niibot_bot BYPASSRLS;
