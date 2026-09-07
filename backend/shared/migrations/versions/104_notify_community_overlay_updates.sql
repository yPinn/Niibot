-- Wake Live Display stream consumers after durable state commits.
-- The table remains the data source; NOTIFY contains no capability or user content.

CREATE OR REPLACE FUNCTION notify_community_overlay_update()
RETURNS TRIGGER AS $$
DECLARE
    target_channel_id TEXT;
    update_kind TEXT;
BEGIN
    target_channel_id := NEW.channel_id;
    update_kind := CASE TG_TABLE_NAME
        WHEN 'community_overlay_events' THEN 'event'
        WHEN 'community_overlay_profiles' THEN 'theme'
        ELSE 'access'
    END;
    PERFORM pg_notify('community_overlay_updates',
        json_build_object('channel_id', target_channel_id, 'kind', update_kind)::TEXT);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_notify_community_overlay_event ON community_overlay_events;
CREATE TRIGGER trg_notify_community_overlay_event
AFTER INSERT ON community_overlay_events
FOR EACH ROW EXECUTE FUNCTION notify_community_overlay_update();

DROP TRIGGER IF EXISTS trg_notify_community_overlay_theme ON community_overlay_profiles;
CREATE TRIGGER trg_notify_community_overlay_theme
AFTER UPDATE OF published_revision_id ON community_overlay_profiles
FOR EACH ROW
WHEN (OLD.published_revision_id IS DISTINCT FROM NEW.published_revision_id)
EXECUTE FUNCTION notify_community_overlay_update();

DROP TRIGGER IF EXISTS trg_notify_community_overlay_access ON community_overlay_channels;
CREATE TRIGGER trg_notify_community_overlay_access
AFTER UPDATE OF public_key, enabled ON community_overlay_channels
FOR EACH ROW
WHEN (OLD.public_key IS DISTINCT FROM NEW.public_key OR OLD.enabled IS DISTINCT FROM NEW.enabled)
EXECUTE FUNCTION notify_community_overlay_update();
