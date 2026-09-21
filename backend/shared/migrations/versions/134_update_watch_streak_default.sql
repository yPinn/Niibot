-- Migration 134: make the Watch Streak response thank the viewer.
--
-- Only rows that still use the previously shipped default are rewritten.
-- Channel-specific templates remain untouched.

UPDATE event_configs
SET message_template = '感謝 $(@user) 的陪伴，已連續觀看 $(streak) 場直播！'
WHERE event_type = 'watch_streak'
  AND message_template = '恭喜 $(@user) 連續觀看 $(streak) 場直播，獲得 $(points) 點忠誠點數！';
