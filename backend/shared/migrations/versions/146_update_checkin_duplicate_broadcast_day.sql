-- Describe the check-in key as a broadcast day because a stream may cross
-- midnight. Preserve broadcaster customizations by updating only the previous
-- default installed by migration 094.
ALTER TABLE checkin_settings
    ALTER COLUMN duplicate_template
    SET DEFAULT '$(@user) 本直播日已經簽到過了，目前累積 $(count) 天！';

UPDATE checkin_settings
SET duplicate_template = '$(@user) 本直播日已經簽到過了，目前累積 $(count) 天！'
WHERE duplicate_template = '$(@user) 今天已經簽到過了，目前累積 $(count) 天！';
