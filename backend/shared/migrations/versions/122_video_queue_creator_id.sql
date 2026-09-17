-- 122: creator identity columns for video_queue — the "creator_id plumbing"
-- video_queue_blocklist (migration 110) already reserved a 'creator' kind
-- for, but never had data to match against. Until now, kind='creator' was a
-- stub aliased to kind='video' (see shared/repositories/video_queue.py's
-- _blocklist_match) because no per-platform channel/uploader identity was
-- captured anywhere. This adds that identity to the queue row itself, so
-- blocklist checks (and future features) can match on it without a second
-- fetch:
--
--   creator_id   — platform-native, stable identity of who made the content
--                  (YouTube channelId, Bilibili owner.mid, Twitch Clip
--                  broadcaster_id, Instagram Reel's @handle — that platform
--                  has no numeric id available to this integration).
--   creator_name — display label for the dashboard (channel title / owner
--                  name / broadcaster_name / handle). Not matched against;
--                  purely cosmetic, same role as video_queue_blocklist.label.
--
-- Both nullable: a platform this session's metadata fetch couldn't resolve
-- (transient failure, or a fetch predating this migration) simply has no
-- creator-based blocklist rule ever match it — same fail-open posture as
-- every other best-effort metadata field on this table.

ALTER TABLE video_queue ADD COLUMN creator_id TEXT;
ALTER TABLE video_queue ADD COLUMN creator_name TEXT;
