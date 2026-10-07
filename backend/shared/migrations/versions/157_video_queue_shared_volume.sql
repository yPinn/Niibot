-- 157: one shared Video Queue volume.
--
-- Live streams (直播播放, migration 155) no longer have their own volume: they
-- play at the same volume as queue videos — balancing them is the streamer's
-- call in OBS, not a second Niibot knob. The live row still snapshots the
-- shared value (video_queue_inserts.volume_percent) so a change reaches a
-- running stream through its NOTIFY.
--
-- The shared default drops from 100 to 50: full volume next to the streamer's
-- own audio is almost always too loud. Only new settings rows get it — an
-- existing 100 can't be told apart from a deliberate choice.

ALTER TABLE video_queue_settings
    DROP CONSTRAINT IF EXISTS chk_video_queue_insert_volume_percent;

ALTER TABLE video_queue_settings
    DROP COLUMN IF EXISTS insert_volume_percent;

ALTER TABLE video_queue_settings
    ALTER COLUMN volume_percent SET DEFAULT 50;
