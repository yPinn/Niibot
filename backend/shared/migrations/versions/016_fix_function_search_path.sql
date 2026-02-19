-- Migration 016: Fix mutable search_path on all trigger functions
-- Description: Sets search_path = public on all plpgsql trigger functions
--              to resolve Supabase linter security warnings.

-- From 000_initial_schema
CREATE OR REPLACE FUNCTION fn_update_updated_at()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_notify_channel_toggle()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
DECLARE
    payload TEXT;
BEGIN
    IF NEW.enabled IS DISTINCT FROM OLD.enabled THEN
        payload := json_build_object(
            'channel_id',   NEW.channel_id,
            'channel_name', NEW.channel_name,
            'enabled',      NEW.enabled
        )::text;
        PERFORM pg_notify('channel_toggle', payload);
    END IF;
    RETURN NEW;
END;
$$;

-- From 003_new_token_notify
CREATE OR REPLACE FUNCTION fn_notify_new_token()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('new_token', json_build_object(
        'user_id', NEW.user_id
    )::text);
    RETURN NEW;
END;
$$;

-- From 014_config_change_notify
CREATE OR REPLACE FUNCTION fn_notify_config_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('config_change', json_build_object(
        'table', TG_TABLE_NAME,
        'channel_id', NEW.channel_id
    )::text);
    RETURN NEW;
END;
$$;

CREATE OR REPLACE FUNCTION fn_notify_config_delete()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    PERFORM pg_notify('config_change', json_build_object(
        'table', TG_TABLE_NAME,
        'channel_id', OLD.channel_id
    )::text);
    RETURN OLD;
END;
$$;

CREATE OR REPLACE FUNCTION fn_notify_channel_defaults_change()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = public
AS $$
BEGIN
    IF NEW.default_cooldown IS DISTINCT FROM OLD.default_cooldown THEN
        PERFORM pg_notify('config_change', json_build_object(
            'table', 'channels',
            'channel_id', NEW.channel_id
        )::text);
    END IF;
    RETURN NEW;
END;
$$;
