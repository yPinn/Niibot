ALTER TABLE viewer_attendance_streaks
    ADD COLUMN IF NOT EXISTS best_streak INT NOT NULL DEFAULT 0;

-- Seed best_streak from current streak_count for all existing rows
UPDATE viewer_attendance_streaks
SET best_streak = streak_count
WHERE best_streak = 0 AND streak_count > 0;
