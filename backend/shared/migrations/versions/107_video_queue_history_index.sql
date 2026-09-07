-- Index the dashboard "played" history read: terminal rows (done/skipped) for
-- one channel, newest ended_at first, keyset-paged on ended_at.
--
-- Partial (status filter baked in) so it stays small — active queue rows and
-- the retention DELETE both benefit too. No new table: history has always been
-- the terminal rows left in video_queue, they just had no read path.

CREATE INDEX IF NOT EXISTS idx_video_queue_channel_ended
    ON video_queue (channel_id, ended_at DESC)
    WHERE status IN ('done', 'skipped');
