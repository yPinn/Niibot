-- Persist the next Twitch credential validation time so API replicas can
-- atomically claim small, evenly-drained batches instead of rechecking every
-- credential in the same startup/minute boundary.
--
-- Existing rows intentionally remain NULL.  NULL means "due now", and the
-- runtime drains them through the bounded SKIP LOCKED claimant; there is no
-- migration-time provider fan-out or mass data rewrite.

ALTER TABLE tokens
    ADD COLUMN IF NOT EXISTS next_validation_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_tokens_validation_schedule_due
    ON tokens (next_validation_at NULLS FIRST, user_id, token_type)
    WHERE invalidated_at IS NULL;

COMMENT ON COLUMN tokens.next_validation_at IS
    'Next provider validation time; NULL is due and a short future value is an in-flight lease';
