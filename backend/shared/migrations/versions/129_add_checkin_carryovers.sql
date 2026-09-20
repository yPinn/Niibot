-- Additive aggregate carry-over and rebuildable daily streak projection.
-- Imported summary counts intentionally do not create fake viewer_checkins or card draws.

CREATE TABLE checkin_import_batches (
    id                    UUID NOT NULL DEFAULT gen_random_uuid(),
    channel_id            TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    source                 TEXT NOT NULL CHECK (source ~ '^[a-z0-9]+(?:-[a-z0-9]+)*$'),
    source_format          TEXT NOT NULL
                           CHECK (source_format IN ('csv', 'tsv', 'xlsx', 'google_sheets')),
    granularity            TEXT NOT NULL DEFAULT 'aggregate'
                           CHECK (granularity = 'aggregate'),
    source_timezone        TEXT NOT NULL CHECK (char_length(source_timezone) BETWEEN 1 AND 64),
    through_date           DATE NOT NULL,
    content_sha256         TEXT NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    idempotency_key        TEXT NOT NULL CHECK (idempotency_key ~ '^[a-f0-9]{64}$'),
    applied_by_user_id     UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    selected_rows          INT NOT NULL CHECK (selected_rows > 0),
    imported_rows          INT NOT NULL CHECK (imported_rows >= 0),
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    UNIQUE (id, channel_id),
    UNIQUE (channel_id, idempotency_key)
);

CREATE TABLE viewer_checkin_carryovers (
    channel_id            TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id               TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    import_batch_id       UUID NOT NULL,
    source_username       TEXT NOT NULL CHECK (char_length(source_username) BETWEEN 1 AND 128),
    source_display_name   TEXT CHECK (
                              source_display_name IS NULL
                              OR char_length(source_display_name) <= 128
                          ),
    carried_total_days    BIGINT NOT NULL CHECK (carried_total_days > 0),
    last_source_date      DATE NOT NULL,
    source_current_streak BIGINT CHECK (
                              source_current_streak IS NULL
                              OR (
                                  source_current_streak >= 0
                                  AND source_current_streak <= carried_total_days
                              )
                          ),
    source_daily_order    INT CHECK (source_daily_order IS NULL OR source_daily_order > 0),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel_id, user_id),
    FOREIGN KEY (import_batch_id, channel_id)
        REFERENCES checkin_import_batches(id, channel_id) ON DELETE RESTRICT
);

CREATE INDEX idx_viewer_checkin_carryovers_channel_rank
    ON viewer_checkin_carryovers (channel_id, carried_total_days DESC, last_source_date DESC);

CREATE TABLE viewer_daily_checkin_streaks (
    channel_id        TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    user_id           TEXT NOT NULL CHECK (char_length(user_id) BETWEEN 1 AND 128),
    current_streak    BIGINT NOT NULL CHECK (current_streak >= 0),
    last_checkin_date DATE NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (channel_id, user_id)
);

-- Rebuild the latest consecutive date island for every existing viewer.
WITH latest_island AS (
    SELECT DISTINCT ON (channel_id, user_id)
        channel_id,
        user_id,
        COUNT(*) OVER (PARTITION BY channel_id, user_id, island_key) AS current_streak,
        MAX(checkin_date) OVER (PARTITION BY channel_id, user_id, island_key) AS last_checkin_date
    FROM (
        SELECT
            channel_id,
            user_id,
            checkin_date,
            checkin_date
                - ROW_NUMBER() OVER (
                    PARTITION BY channel_id, user_id ORDER BY checkin_date
                )::INT AS island_key
        FROM (
            SELECT DISTINCT channel_id, user_id, checkin_date
            FROM viewer_checkins
        ) AS unique_dates
    ) AS islands
    ORDER BY channel_id, user_id, last_checkin_date DESC
)
INSERT INTO viewer_daily_checkin_streaks
    (channel_id, user_id, current_streak, last_checkin_date)
SELECT channel_id, user_id, current_streak, last_checkin_date
FROM latest_island;

CREATE POLICY p_checkin_import_batches_tenant ON checkin_import_batches
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_viewer_checkin_carryovers_tenant ON viewer_checkin_carryovers
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

CREATE POLICY p_viewer_daily_checkin_streaks_tenant ON viewer_daily_checkin_streaks
    USING (fn_tenant_match(channel_id))
    WITH CHECK (fn_tenant_match(channel_id));

-- RLS activation remains staged with the rest of the tenant-owned schema.
