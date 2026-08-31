-- Bind redemption actions to Twitch's stable reward id and add daily check-in.
-- Existing title-based rows remain nullable and continue through the legacy
-- compatibility path until each tenant explicitly selects a reward again.

ALTER TABLE redemption_configs
    ADD COLUMN reward_id TEXT
    CHECK (reward_id IS NULL OR char_length(reward_id) BETWEEN 1 AND 128);

ALTER TABLE redemption_configs
    DROP CONSTRAINT IF EXISTS redemption_configs_action_type_check;

ALTER TABLE redemption_configs
    ADD CONSTRAINT redemption_configs_action_type_check
    CHECK (
        action_type IN (
            'vip',
            'first',
            'niibot_auth',
            'game_queue',
            'video_queue',
            'checkin'
        )
    );

-- One Twitch reward must not dispatch multiple Niibot actions in one tenant.
CREATE UNIQUE INDEX uq_redemption_configs_channel_reward_id
    ON redemption_configs (channel_id, reward_id)
    WHERE reward_id IS NOT NULL;
