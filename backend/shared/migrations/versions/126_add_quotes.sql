-- 126: Per-channel quote board (!quote / !quote add / !quote del).
--
-- quote_number is a small channel-scoped sequence (1, 2, 3, ...) so chat can
-- reference "!quote 5" instead of the global id — computed at insert time
-- from the channel's current max (single-statement INSERT ... SELECT, so the
-- read and the write are atomic). The UNIQUE constraint is a guard against
-- the theoretical concurrent-insert race, not the primary mechanism.

CREATE TABLE quotes (
    id           BIGSERIAL PRIMARY KEY,
    channel_id   TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    quote_number INT NOT NULL CHECK (quote_number > 0),
    quote_text   TEXT NOT NULL CHECK (char_length(quote_text) BETWEEN 1 AND 450),
    created_by   TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (channel_id, quote_number)
);

CREATE INDEX idx_quotes_channel ON quotes (channel_id);

-- Staged, not enabled — same convention as migration 101/125.
CREATE POLICY p_quotes_tenant ON quotes
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));
