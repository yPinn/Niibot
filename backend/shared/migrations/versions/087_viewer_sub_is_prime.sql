-- Migration 087: track whether a viewer's subscription is a Prime sub.
--
-- Written by the twitch bot's channel.chat.notification handler (the sub /
-- resub / prime_paid_upgrade notices — the only source carrying is_prime).
-- Nulled by upsert_viewer_subscription_end when a sub lapses.
-- Read by AnalyticsRepository.get_plus_program_estimate — the Plus Program
-- point tally excludes Prime and gifted subs.
--
-- Tri-state: TRUE = Prime, FALSE = paid recurring, NULL = not yet observed via
-- a chat notification (every row is NULL until its owner subs/resubs live).

ALTER TABLE viewer_channel_status ADD COLUMN IF NOT EXISTS sub_is_prime BOOLEAN;

COMMENT ON COLUMN viewer_channel_status.sub_is_prime IS
    'TRUE = Prime sub, FALSE = paid recurring, NULL = unknown (never seen via '
    'channel.chat.notification). Helix Get Broadcaster Subscriptions cannot '
    'distinguish Prime, so this is only populated for live sub/resub events.';
