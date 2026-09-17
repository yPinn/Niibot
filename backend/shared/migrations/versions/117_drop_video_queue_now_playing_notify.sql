-- Migration 117: Stop announcing "now playing" in chat when a video starts.
--
-- Migration 116 added a trigger that fired pg_notify('video_queue_now_playing')
-- on every transition into 'playing', which the bot turned into a chat line.
-- In real use that is one bot message per video for the whole stream, which
-- reads as spam in a busy chat and drowns out the messages viewers actually
-- asked for. Viewers who want to know what is playing can still ask with !np.
--
-- Dropping the trigger rather than only removing the bot's listener: leaving it
-- in place would keep every play transition doing pg_notify work that nothing
-- consumes.

DROP TRIGGER IF EXISTS trg_notify_video_queue_now_playing ON video_queue;
DROP FUNCTION IF EXISTS notify_video_queue_now_playing();
