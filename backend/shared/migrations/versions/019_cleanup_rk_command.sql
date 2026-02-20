-- Remove obsolete 'rk' builtin command entries (renamed to 'tft')
DELETE FROM command_configs
WHERE command_name = 'rk'
  AND command_type = 'builtin';
