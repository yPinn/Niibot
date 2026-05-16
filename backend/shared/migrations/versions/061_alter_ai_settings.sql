-- Migration 061: Replace monolithic system_prompt with structured AI settings fields
ALTER TABLE ai_settings
    ADD COLUMN IF NOT EXISTS bot_name      TEXT        NOT NULL DEFAULT 'Twitch 聊天室機器人',
    ADD COLUMN IF NOT EXISTS persona       TEXT        NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS response_lang TEXT        NOT NULL DEFAULT 'zh-tw',
    ADD COLUMN IF NOT EXISTS refusal_style TEXT        NOT NULL DEFAULT 'humorous',
    ADD COLUMN IF NOT EXISTS enabled_emotes TEXT[]     NOT NULL DEFAULT '{}';

ALTER TABLE ai_settings
    ADD CONSTRAINT ai_settings_response_lang_check
        CHECK (response_lang IN ('zh-tw', 'en', 'auto')),
    ADD CONSTRAINT ai_settings_refusal_style_check
        CHECK (refusal_style IN ('humorous', 'polite'));

ALTER TABLE ai_settings DROP COLUMN IF EXISTS system_prompt;
