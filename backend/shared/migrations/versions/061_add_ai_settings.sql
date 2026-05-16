-- Migration 060: Add ai_settings for per-channel AI character configuration
CREATE TABLE ai_settings (
    channel_id     TEXT        PRIMARY KEY REFERENCES channels(channel_id) ON DELETE CASCADE,
    bot_name       TEXT        NOT NULL DEFAULT 'Twitch 聊天室機器人',
    persona        TEXT        NOT NULL DEFAULT '',
    response_lang  TEXT        NOT NULL DEFAULT 'zh-tw'
                               CHECK (response_lang IN ('zh-tw', 'en', 'auto')),
    refusal_style  TEXT        NOT NULL DEFAULT 'humorous'
                               CHECK (refusal_style IN ('humorous', 'polite')),
    max_tokens     INT         NOT NULL DEFAULT 250
                               CHECK (max_tokens BETWEEN 50 AND 500),
    enabled_emotes TEXT[]      NOT NULL DEFAULT '{}',
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
