-- Let each channel customize the "頭香" (first-of-the-day) redemption
-- announcement instead of the hardcoded "恭喜你搶到沙發！" text. NOT NULL
-- DEFAULT backfills existing rows to today's exact wording, so this migration
-- changes no observed behavior on its own and every layer (bot/API/frontend)
-- can treat the columns as always-present rather than null-vs-default.
ALTER TABLE redemption_configs
    ADD COLUMN first_message TEXT NOT NULL DEFAULT '$(@user) 恭喜你搶到沙發！'
    CHECK (char_length(first_message) BETWEEN 1 AND 300),
    ADD COLUMN first_announce_color TEXT NOT NULL DEFAULT 'primary'
    CHECK (first_announce_color IN ('blue', 'green', 'orange', 'purple', 'primary'));
