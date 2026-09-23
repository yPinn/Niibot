-- Preserve immutable card draws except when their source check-in has already
-- been deleted in the same transaction by the owner-only data reset flow.
-- The FK is DEFERRABLE, so the transaction must remove the matching draws
-- before commit or the complete reset rolls back atomically.

CREATE OR REPLACE FUNCTION fn_prevent_viewer_card_draw_change()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND (
           NOT EXISTS (
               SELECT 1
               FROM channels
               WHERE channel_id = OLD.channel_id
           )
           OR NOT EXISTS (
               SELECT 1
               FROM viewer_checkins
               WHERE channel_id = OLD.channel_id
                 AND user_id = OLD.user_id
                 AND id = OLD.checkin_id
           )
       ) THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'viewer card draws are immutable';
END;
$$ LANGUAGE plpgsql;
