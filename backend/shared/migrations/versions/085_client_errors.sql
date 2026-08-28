-- 085: client_errors — frontend error telemetry sink.
--
-- ## Why
-- Frontend errors were invisible in production: ErrorBoundary only
-- console.error'd in dev, and there was no window.onerror / unhandledrejection
-- handler at all. When a user reported "the page broke" there was nothing to
-- look at.
--
-- This table is the sink for POST /api/client-errors. Rows are raw events (not
-- pre-aggregated) so an individual stack trace is always recoverable; the admin
-- view aggregates with GROUP BY fingerprint.
--
-- request_id is the join key back to the structured backend logs / the error
-- envelope the user was shown.
--
-- Retention: a 24h background loop deletes rows older than 14 days, and each
-- insert has a 1/200 chance of trimming to the most recent 50k rows (guards
-- against a release that makes every client error every second).

CREATE TABLE IF NOT EXISTS client_errors (
    id               BIGSERIAL PRIMARY KEY,
    occurred_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    kind             TEXT NOT NULL
                     CHECK (kind IN ('error', 'unhandledrejection', 'react', 'api')),
    fingerprint      TEXT NOT NULL,
    message          TEXT NOT NULL,
    stack            TEXT,
    component_stack  TEXT,
    url              TEXT NOT NULL,
    route            TEXT,
    request_id       TEXT,
    error_code       TEXT,
    http_status      INT,
    user_id          UUID REFERENCES users(id) ON DELETE SET NULL,
    user_agent       TEXT,
    app_version      TEXT,
    ip_hash          TEXT
);

CREATE INDEX IF NOT EXISTS idx_client_errors_occurred_at
    ON client_errors (occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_errors_fingerprint
    ON client_errors (fingerprint, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_client_errors_request_id
    ON client_errors (request_id) WHERE request_id IS NOT NULL;
