-- Add FK constraints from all Twitch feature tables to channels(channel_id).
-- ON DELETE CASCADE ensures that removing a channel cleans up all associated data.
--
-- Run after verifying no orphan rows exist:
--   SELECT DISTINCT channel_id FROM command_configs
--   WHERE channel_id NOT IN (SELECT channel_id FROM channels);
-- (repeat for each table)

ALTER TABLE command_configs
    ADD CONSTRAINT fk_command_configs_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE redemption_configs
    ADD CONSTRAINT fk_redemption_configs_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE event_configs
    ADD CONSTRAINT fk_event_configs_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE timers
    ADD CONSTRAINT fk_timers_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE message_triggers
    ADD CONSTRAINT fk_message_triggers_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE game_queue_entries
    ADD CONSTRAINT fk_game_queue_entries_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE game_queue_settings
    ADD CONSTRAINT fk_game_queue_settings_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE video_queue
    ADD CONSTRAINT fk_video_queue_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;

ALTER TABLE video_queue_settings
    ADD CONSTRAINT fk_video_queue_settings_channel
    FOREIGN KEY (channel_id) REFERENCES channels(channel_id) ON DELETE CASCADE;
