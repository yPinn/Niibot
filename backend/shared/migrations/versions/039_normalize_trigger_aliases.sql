-- Normalize trigger aliases from comma-separated TEXT column to a proper table.
-- API surface (comma-separated string) is preserved at the application layer.

CREATE TABLE trigger_aliases (
    id         SERIAL PRIMARY KEY,
    trigger_id INT  NOT NULL REFERENCES message_triggers(id) ON DELETE CASCADE,
    alias      TEXT NOT NULL,
    UNIQUE (trigger_id, alias)
);

CREATE INDEX idx_trigger_aliases_trigger_id ON trigger_aliases (trigger_id);

-- Migrate existing comma-separated data
INSERT INTO trigger_aliases (trigger_id, alias)
SELECT id, trim(a)
FROM message_triggers,
     unnest(string_to_array(aliases, ',')) AS a
WHERE aliases IS NOT NULL
  AND trim(aliases) <> ''
  AND trim(a) <> '';

-- Drop the old column
ALTER TABLE message_triggers DROP COLUMN aliases;
