-- 057: Add copy_count to crosshairs for tracking how many times each code has been copied

ALTER TABLE crosshairs ADD COLUMN IF NOT EXISTS copy_count INT NOT NULL DEFAULT 0;
