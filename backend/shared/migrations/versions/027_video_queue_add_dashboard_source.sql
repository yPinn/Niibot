-- Migration 027: Allow 'dashboard' as a valid source in video_queue

ALTER TABLE video_queue
    DROP CONSTRAINT IF EXISTS video_queue_source_check;

ALTER TABLE video_queue
    ADD CONSTRAINT video_queue_source_check
    CHECK (source IN ('chat', 'redemption', 'dashboard'));
