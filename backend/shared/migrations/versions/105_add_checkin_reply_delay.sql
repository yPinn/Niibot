-- Chat replies go out over IRC almost instantly, but the Live Display animation
-- only becomes visible once Twitch's broadcast pipeline (encode + CDN) delivers
-- that frame to viewers. That delay is outside the bot's control and varies by
-- the channel's stream latency mode, so let each channel opt into delaying its
-- own check-in reply to roughly match.
ALTER TABLE checkin_settings
    ADD COLUMN reply_delay_seconds SMALLINT NOT NULL DEFAULT 0
    CHECK (reply_delay_seconds BETWEEN 0 AND 30);
