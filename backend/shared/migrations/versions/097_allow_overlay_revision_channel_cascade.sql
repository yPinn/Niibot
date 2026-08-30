-- Keep direct revision deletion forbidden without blocking channel lifecycle cleanup.

CREATE OR REPLACE FUNCTION fn_prevent_community_overlay_revision_update()
RETURNS TRIGGER AS $$
BEGIN
    -- A channel DELETE invokes the FK cascade from a parent trigger (depth > 1).
    -- Direct DELETE and every UPDATE remain forbidden.
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'community overlay revisions are immutable';
END;
$$ LANGUAGE plpgsql;
