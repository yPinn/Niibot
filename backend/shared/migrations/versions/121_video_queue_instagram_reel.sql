-- 121: Instagram Reel support for video_queue.
--
-- Reels resolve via the self-hosted InstaFix proxy (docs/integrations/instafix.md):
-- title/thumbnail are fetched at enqueue time, the direct CDN mp4 URL is
-- resolved fresh at play time (it's signed and expires, same as Twitch Clip's
-- source URL) via GET .../entries/{id}/reel-source. No duration/view_count is
-- available, so metadata_best_effort applies the same way it does for Bilibili.

ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_video_type_check;
ALTER TABLE video_queue ADD CONSTRAINT video_queue_video_type_check
    CHECK (video_type IN ('youtube', 'twitch_clip', 'twitch_vod', 'bilibili', 'instagram_reel'));
