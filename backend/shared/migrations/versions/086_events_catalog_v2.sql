-- Migration 086: events catalog v2 — gift_recipient type, refreshed defaults
--
-- Ships alongside the shared.events rework: subscribe/resub/gift greetings move
-- to channel.chat.notification (gaining is_prime / gifted-resub / per-recipient
-- data), templates gain $(@user) mentions, a $(note) disclosure var and
-- optional [[ ]] segments, and a new opt-in `gift_recipient` event.
--
-- Only rows that still hold a known shipped default are rewritten; a channel's
-- customised template is never touched.

ALTER TABLE event_configs DROP CONSTRAINT IF EXISTS event_configs_event_type_check;
ALTER TABLE event_configs ADD CONSTRAINT event_configs_event_type_check
    CHECK (event_type IN ('follow', 'subscribe', 'resub', 'gift_sub', 'gift_recipient', 'raid', 'bits'));

UPDATE event_configs SET message_template = '感謝 $(@user) 的訂閱$(note)！'
 WHERE event_type = 'subscribe' AND message_template = '感謝 $(user) 的訂閱！';

UPDATE event_configs
   SET message_template =
       '感謝 $(@user) 訂閱滿 $(total_months) 個月[[，已連續 $(streak) 個月]]$(note)！'
 WHERE event_type = 'resub'
   AND message_template IN (
       '感謝 $(user) 連續訂閱 $(months) 個月！',
       '感謝 $(user) 訂閱滿 $(total_months) 個月！'
   );

UPDATE event_configs
   SET message_template =
       '感謝 $(@user) 送出 $(total) 份訂閱$(note)[[，累計已送 $(cumulative) 份]]！'
 WHERE event_type = 'gift_sub' AND message_template = '感謝 $(user) 贈送了 $(total) 個訂閱！';

UPDATE event_configs
   SET message_template = '感謝 $(@user) 的 $(amount) 小奇點應援[[（留言：$(message)）]]！'
 WHERE event_type = 'bits' AND message_template = '感謝 $(user) 投出了 $(amount) 小奇點！';

UPDATE event_configs
   SET message_template = '感謝 $(@user) 帶團降落，歡迎 $(count) 位新朋友！'
 WHERE event_type = 'raid' AND message_template = '$(user) 帶了 $(count) 個新朋友降落！';

-- bits.tiers was declared in the old catalog but never read by any code. The
-- API now projects options onto the catalog schema; clear the stored blob too.
UPDATE event_configs SET options = '{}'::jsonb
 WHERE event_type = 'bits' AND options ? 'tiers';

COMMENT ON COLUMN event_configs.options IS
    'JSONB options per event type, projected onto shared.events options_schema '
    'by EventConfigService. raid: {"auto_shoutout": bool}. '
    'gift_recipient: {"skip_bombs": bool}.';
