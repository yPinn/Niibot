-- Add game_id to stream_sessions table
-- Box art URL is not stored - frontend generates it dynamically using the game_id

ALTER TABLE stream_sessions
ADD COLUMN IF NOT EXISTS game_id TEXT;

-- Create index for game lookups
CREATE INDEX IF NOT EXISTS idx_sessions_game
ON stream_sessions(game_id)
WHERE game_id IS NOT NULL;

-- Add comment
COMMENT ON COLUMN stream_sessions.game_id IS 'Twitch game/category ID from Helix API. Box art URL format: https://static-cdn.jtvnw.net/ttv-boxart/{game_id}-{width}x{height}.jpg';
