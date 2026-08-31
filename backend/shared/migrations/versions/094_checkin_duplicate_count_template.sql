-- Duplicate replies should return the same channel-scoped cumulative count as
-- successful check-ins. Preserve tenant customizations by updating only rows
-- that still match the original migration 093 default.
ALTER TABLE checkin_settings
    ALTER COLUMN duplicate_template
    SET DEFAULT '$(@user) 今天已經簽到過了，目前累積 $(count) 天！';

UPDATE checkin_settings
SET duplicate_template = '$(@user) 今天已經簽到過了，目前累積 $(count) 天！'
WHERE duplicate_template = '$(@user) 今天已經簽到過了！';
