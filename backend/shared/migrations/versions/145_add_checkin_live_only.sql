-- New channels default to live-only check-ins. Existing channels keep their
-- current offline-capable behavior until the broadcaster explicitly opts in.
ALTER TABLE checkin_settings
    ADD COLUMN live_only BOOLEAN NOT NULL DEFAULT TRUE;

UPDATE checkin_settings SET live_only = FALSE;

INSERT INTO checkin_settings (channel_id, live_only)
SELECT channel_id, FALSE FROM channels
ON CONFLICT (channel_id) DO NOTHING;
