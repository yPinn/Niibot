ALTER TABLE ai_settings
    ALTER COLUMN catchphrase_frequency SET DEFAULT 'off',
    ALTER COLUMN refusal_style SET DEFAULT 'polite',
    ALTER COLUMN cooldown SET DEFAULT 30;
