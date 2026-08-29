-- Migration 086: fix the resub default greeting and drop the dead bits.tiers option
--
-- The shipped resub default used $(months), which is EventSub's duration_months
-- (~1 for a normal monthly resub) — it rendered "訂閱滿 1 個月" for everyone. The
-- catalog now exposes $(total_months) (cumulative_months). Only rows that still
-- hold the exact old default are touched; customised templates are left alone.

UPDATE event_configs
   SET message_template = '感謝 $(user) 訂閱滿 $(total_months) 個月！'
 WHERE event_type = 'resub'
   AND message_template = '感謝 $(user) 連續訂閱 $(months) 個月！';

-- bits.tiers was declared in the catalog but never read by any code. The API
-- now projects options onto the catalog schema, but clear the stored blob too.
UPDATE event_configs
   SET options = '{}'::jsonb
 WHERE event_type = 'bits'
   AND options ? 'tiers';

COMMENT ON COLUMN event_configs.options IS
    'JSONB options per event type, projected onto shared.events options_schema '
    'by EventConfigService. raid: {"auto_shoutout": bool}.';
