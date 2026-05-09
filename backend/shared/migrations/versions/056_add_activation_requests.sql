-- 056: Add activation_requests table for manual approval flow
--
-- activation_requests – users who requested activation without an OTP code;
--                       owner reviews and approves/rejects from the Admin panel.

CREATE TABLE IF NOT EXISTS activation_requests (
    id               SERIAL       PRIMARY KEY,
    user_id          UUID         NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform         TEXT         NOT NULL DEFAULT 'twitch',
    platform_user_id TEXT         NOT NULL,
    note             TEXT         NOT NULL DEFAULT '',
    status           TEXT         NOT NULL DEFAULT 'pending'
                     CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at       TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    reviewed_at      TIMESTAMPTZ
);

-- Only one pending request per user at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_activation_requests_one_pending
    ON activation_requests (user_id)
    WHERE status = 'pending';
