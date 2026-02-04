-- Add game_id to stream_sessions table
-- Box art URL is not stored — frontend generates it dynamically using the game_id
-- Format: https://static-cdn.jtvnw.net/ttv-boxart/{game_id}-{width}x{height}.jpg

ALTER TABLE stream_sessions
ADD COLUMN IF NOT EXISTS game_id TEXT;

CREATE INDEX IF NOT EXISTS idx_sessions_game
ON stream_sessions(game_id)
WHERE game_id IS NOT NULL;

COMMENT ON COLUMN stream_sessions.game_id IS
    'Twitch game/category ID from Helix API. '
    'Box art URL: https://static-cdn.jtvnw.net/ttv-boxart/{game_id}-{width}x{height}.jpg';
