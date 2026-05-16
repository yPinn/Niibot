-- Migration 052: Add 'resub' and 'gift_sub' as valid event types in event_configs

ALTER TABLE event_configs DROP CONSTRAINT IF EXISTS event_configs_event_type_check;
ALTER TABLE event_configs ADD CONSTRAINT event_configs_event_type_check
    CHECK (event_type IN ('follow', 'subscribe', 'resub', 'gift_sub', 'raid', 'bits'));

COMMENT ON COLUMN event_configs.options IS
    'JSONB options per event type. '
    'raid: {"auto_shoutout": bool}. '
    'bits: {"tiers": [{"min_bits": int, "max_bits": int, "message": str}, ...]}';
