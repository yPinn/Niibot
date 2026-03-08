-- Normalize command aliases from comma-separated TEXT column to a proper table.
-- API surface (comma-separated string) is preserved at the application layer.

CREATE TABLE command_aliases (
    id         SERIAL PRIMARY KEY,
    command_id INT  NOT NULL REFERENCES command_configs(id) ON DELETE CASCADE,
    alias      TEXT NOT NULL,
    UNIQUE (command_id, alias)
);

CREATE INDEX idx_command_aliases_command_id ON command_aliases (command_id);

-- Migrate existing comma-separated data
INSERT INTO command_aliases (command_id, alias)
SELECT id, trim(a)
FROM command_configs,
     unnest(string_to_array(aliases, ',')) AS a
WHERE aliases IS NOT NULL
  AND trim(aliases) <> ''
  AND trim(a) <> '';

-- Drop the old column
ALTER TABLE command_configs DROP COLUMN aliases;
