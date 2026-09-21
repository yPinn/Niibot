-- Migration 130: allow configurable Twitch Watch Streak share notifications.
--
-- Existing channel rows are left untouched. EventConfigRepository.ensure_defaults
-- inserts the disabled default for each channel the next time its event settings
-- are loaded.

ALTER TABLE event_configs DROP CONSTRAINT IF EXISTS event_configs_event_type_check;
ALTER TABLE event_configs ADD CONSTRAINT event_configs_event_type_check
    CHECK (event_type IN (
        'follow',
        'subscribe',
        'resub',
        'gift_sub',
        'gift_recipient',
        'watch_streak',
        'raid',
        'bits'
    ));
