-- 152: Reserve newly shortened Chinese builtin aliases without losing custom data.
--
-- The API and chat manager reject these names for new custom commands. Existing
-- builtin overrides may also have persisted the former shipped aliases, so move
-- only those exact command/alias pairs to the new defaults. User-added aliases
-- remain untouched. Conflicting custom rows are disabled but keep their response,
-- cooldown, role and aliases so the operator can rename and re-enable them.

WITH alias_mapping(command_name, old_alias, new_alias) AS (
    VALUES
        ('title', '台標', '標題'),
        ('winner', '幸運兒', '抽'),
        ('choose', '選擇', '選'),
        ('del', '刪除', '刪')
)
DELETE FROM command_aliases AS old_alias
USING command_configs AS command, alias_mapping AS mapping
WHERE old_alias.command_id = command.id
  AND command.command_type = 'builtin'
  AND command.command_name = mapping.command_name
  AND old_alias.alias = mapping.old_alias
  AND EXISTS (
      SELECT 1
      FROM command_aliases AS current_alias
      WHERE current_alias.command_id = command.id
        AND current_alias.alias = mapping.new_alias
  );

WITH alias_mapping(command_name, old_alias, new_alias) AS (
    VALUES
        ('title', '台標', '標題'),
        ('winner', '幸運兒', '抽'),
        ('choose', '選擇', '選'),
        ('del', '刪除', '刪')
)
UPDATE command_aliases AS alias
SET alias = mapping.new_alias
FROM command_configs AS command, alias_mapping AS mapping
WHERE alias.command_id = command.id
  AND command.command_type = 'builtin'
  AND command.command_name = mapping.command_name
  AND alias.alias = mapping.old_alias;

WITH concise_alias(name) AS (
    VALUES
        ('刪'),
        ('抽'),
        ('標題'),
        ('選')
)
UPDATE command_configs AS command
SET enabled = FALSE
WHERE command.command_type = 'custom'
  AND command.enabled = TRUE
  AND (
      EXISTS (
          SELECT 1
          FROM concise_alias
          WHERE concise_alias.name = lower(command.command_name)
      )
      OR EXISTS (
          SELECT 1
          FROM command_aliases AS alias
          JOIN concise_alias ON concise_alias.name = lower(alias.alias)
          WHERE alias.command_id = command.id
      )
  );
