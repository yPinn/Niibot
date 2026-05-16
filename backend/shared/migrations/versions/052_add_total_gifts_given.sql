-- Cumulative gift sub count per viewer, sourced from channel.subscription.gift
-- cumulative_total provided by EventSub reflects the lifetime total for this gifter.
ALTER TABLE viewer_channel_status
    ADD COLUMN IF NOT EXISTS total_gifts_given INTEGER NOT NULL DEFAULT 0;
