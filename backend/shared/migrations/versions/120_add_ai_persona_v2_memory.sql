-- Expand AI character settings with structured persona controls and opt-in memory.
ALTER TABLE ai_settings
    ADD COLUMN IF NOT EXISTS audience_reference TEXT NOT NULL DEFAULT '大家',
    ADD COLUMN IF NOT EXISTS tone_preset TEXT NOT NULL DEFAULT 'neutral',
    ADD COLUMN IF NOT EXISTS catchphrase_frequency TEXT NOT NULL DEFAULT 'rare',
    ADD COLUMN IF NOT EXISTS example_replies TEXT[] NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS memory_enabled BOOLEAN NOT NULL DEFAULT false;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_settings_tone_preset_check'
          AND conrelid = 'ai_settings'::regclass
    ) THEN
        ALTER TABLE ai_settings
            ADD CONSTRAINT ai_settings_tone_preset_check
                CHECK (tone_preset IN ('neutral', 'witty', 'energetic', 'tsundere', 'calm'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_settings_catchphrase_frequency_check'
          AND conrelid = 'ai_settings'::regclass
    ) THEN
        ALTER TABLE ai_settings
            ADD CONSTRAINT ai_settings_catchphrase_frequency_check
                CHECK (catchphrase_frequency IN ('off', 'rare', 'occasional'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_settings_example_replies_count_check'
          AND conrelid = 'ai_settings'::regclass
    ) THEN
        ALTER TABLE ai_settings
            ADD CONSTRAINT ai_settings_example_replies_count_check
                CHECK (cardinality(example_replies) <= 3);
    END IF;
END $$;
