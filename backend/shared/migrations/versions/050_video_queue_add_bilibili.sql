-- Migration 049: Add 'bilibili' to video_queue video_type constraint

ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_video_type_check;
ALTER TABLE video_queue ADD CONSTRAINT video_queue_video_type_check
    CHECK (video_type IN ('youtube', 'twitch_clip', 'bilibili'));
