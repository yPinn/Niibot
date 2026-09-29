-- Migration 142: explicit per-occurrence cancellation / replacement state.

ALTER TABLE stream_schedules
    ADD CONSTRAINT uq_stream_schedules_channel_id_id UNIQUE (channel_id, id);

CREATE TABLE stream_schedule_occurrence_exceptions (
    id                      BIGSERIAL PRIMARY KEY,
    channel_id              TEXT NOT NULL REFERENCES channels(channel_id) ON DELETE CASCADE,
    recurring_schedule_id   INT NOT NULL,
    occurrence_date         DATE NOT NULL,
    kind                    TEXT NOT NULL CHECK (kind IN ('cancelled', 'replacement')),
    replacement_schedule_id INT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_stream_schedule_occurrence_exception
        UNIQUE (recurring_schedule_id, occurrence_date),
    CONSTRAINT fk_stream_schedule_occurrence_exception_recurring_tenant
        FOREIGN KEY (channel_id, recurring_schedule_id)
        REFERENCES stream_schedules(channel_id, id) ON DELETE CASCADE,
    CONSTRAINT fk_stream_schedule_occurrence_exception_replacement_tenant
        FOREIGN KEY (channel_id, replacement_schedule_id)
        REFERENCES stream_schedules(channel_id, id) ON DELETE CASCADE,
    CONSTRAINT chk_stream_schedule_occurrence_exception_replacement CHECK (
        (kind = 'cancelled' AND replacement_schedule_id IS NULL)
        OR
        (kind = 'replacement' AND replacement_schedule_id IS NOT NULL)
    )
);

CREATE INDEX idx_stream_schedule_occurrence_exceptions_channel_date
    ON stream_schedule_occurrence_exceptions (channel_id, occurrence_date);

CREATE TRIGGER trg_stream_schedule_occurrence_exceptions_updated_at
    BEFORE UPDATE ON stream_schedule_occurrence_exceptions
    FOR EACH ROW EXECUTE FUNCTION fn_update_updated_at();
