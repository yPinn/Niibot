-- Add self_pronoun and catchphrase to ai_settings for finer persona control.
ALTER TABLE ai_settings
    ADD COLUMN IF NOT EXISTS self_pronoun TEXT NOT NULL DEFAULT '我',
    ADD COLUMN IF NOT EXISTS catchphrase  TEXT NOT NULL DEFAULT '';
