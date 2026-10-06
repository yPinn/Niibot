-- 153: distinguish chat skips from dashboard skips in Video Queue history.
--
-- `!vq skip` used to share skip_current_atomic's hard-coded 'dashboard_skip'
-- end reason, so history and rankings could not tell a chat skip (a mod, or a
-- requester skipping their own video) from the dashboard button. Widen the
-- allowlist from migration 135 with 'chat_skip'; existing rows are unchanged.

ALTER TABLE video_queue
    DROP CONSTRAINT IF EXISTS chk_video_queue_end_reason;

ALTER TABLE video_queue
    ADD CONSTRAINT chk_video_queue_end_reason
        CHECK (
            end_reason IS NULL OR end_reason IN (
                'completed', 'provider_error', 'autoplay_blocked', 'startup_timeout',
                'dashboard_skip', 'chat_skip', 'play_now', 'removed', 'cleared'
            )
        );
