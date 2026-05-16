-- Migration 061: Replace monolithic system_prompt with structured AI settings fields
ALTER TABLE ai_settings
    ADD COLUMN IF NOT EXISTS bot_name      TEXT        NOT NULL DEFAULT 'Twitch 聊天室機器人',
    ADD COLUMN IF NOT EXISTS persona       TEXT        NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS response_lang TEXT        NOT NULL DEFAULT 'zh-tw',
    ADD COLUMN IF NOT EXISTS refusal_style TEXT        NOT NULL DEFAULT 'humorous',
    ADD COLUMN IF NOT EXISTS enabled_emotes TEXT[]     NOT NULL DEFAULT '{}';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_settings_response_lang_check'
          AND conrelid = 'ai_settings'::regclass
    ) THEN
        ALTER TABLE ai_settings
            ADD CONSTRAINT ai_settings_response_lang_check
                CHECK (response_lang IN ('zh-tw', 'en', 'auto'));
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ai_settings_refusal_style_check'
          AND conrelid = 'ai_settings'::regclass
    ) THEN
        ALTER TABLE ai_settings
            ADD CONSTRAINT ai_settings_refusal_style_check
                CHECK (refusal_style IN ('humorous', 'polite'));
    END IF;
END $$;

ALTER TABLE ai_settings DROP COLUMN IF EXISTS system_prompt;
