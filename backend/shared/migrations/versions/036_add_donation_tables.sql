-- 036: Add donation/payment tables for streamer tip integration
--
-- user_payment_configs  – per-streamer, per-platform merchant credentials
-- donation_orders       – individual donation transactions

-- ============================================
-- Table: user_payment_configs
-- ============================================

CREATE TABLE IF NOT EXISTS user_payment_configs (
    user_id             UUID    NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    platform            TEXT    NOT NULL
                        CHECK (platform IN ('ecpay', 'opay', 'paypal', 'newebpay')),
    merchant_id         TEXT    NOT NULL,    -- ECPay/OPay/NewebPay: MerchantID; PayPal: paypal.me URL
    hash_key            TEXT,               -- ECPay/OPay/NewebPay only (NULL for PayPal)
    hash_iv             TEXT,               -- ECPay/OPay/NewebPay only (NULL for PayPal)
    min_amount          INT     NOT NULL DEFAULT 30,
    media_share_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    enabled             BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_user_payment_configs_user_id
    ON user_payment_configs(user_id);

DROP TRIGGER IF EXISTS trg_user_payment_configs_updated_at ON user_payment_configs;
CREATE TRIGGER trg_user_payment_configs_updated_at
    BEFORE UPDATE ON user_payment_configs
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- ============================================
-- Table: donation_orders
-- ============================================

CREATE TABLE IF NOT EXISTS donation_orders (
    id                  UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_id          TEXT        NOT NULL,   -- Twitch platform_user_id for video queue
    platform            TEXT        NOT NULL
                        CHECK (platform IN ('ecpay', 'opay', 'paypal', 'newebpay')),
    merchant_trade_no   TEXT        NOT NULL UNIQUE,   -- 20-char alphanumeric, sent to gateway
    amount              INT         NOT NULL,
    message             TEXT,
    youtube_video_id    TEXT,                          -- 11-char YT ID (NULL if not media share)
    status              TEXT        NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'paid', 'failed')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_donation_orders_user_id
    ON donation_orders(user_id);
CREATE INDEX IF NOT EXISTS idx_donation_orders_merchant_trade_no
    ON donation_orders(merchant_trade_no);

DROP TRIGGER IF EXISTS trg_donation_orders_updated_at ON donation_orders;
CREATE TRIGGER trg_donation_orders_updated_at
    BEFORE UPDATE ON donation_orders
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();

-- ============================================
-- Extend video_queue source to include 'donation'
-- ============================================

ALTER TABLE video_queue DROP CONSTRAINT IF EXISTS video_queue_source_check;
ALTER TABLE video_queue
    ADD CONSTRAINT video_queue_source_check
    CHECK (source IN ('chat', 'redemption', 'dashboard', 'donation'));
