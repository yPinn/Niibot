-- 059: Add code_plain column to activation_codes for frontend display
ALTER TABLE activation_codes ADD COLUMN IF NOT EXISTS code_plain TEXT;
