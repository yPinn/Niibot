-- 147: Repair builtin command roles materialised with generic schema defaults.
--
-- Before the repository fix, toggling a virtual builtin or recording its first
-- usage could insert min_role='everyone' instead of the catalog default.  Only
-- known privileged builtins and only the unsafe generic value are tightened;
-- existing subscriber/vip/moderator/broadcaster overrides are left untouched.

UPDATE command_configs
SET min_role = 'broadcaster'
WHERE command_type = 'builtin'
  AND command_name = 'subcount'
  AND min_role = 'everyone';

UPDATE command_configs
SET min_role = 'moderator'
WHERE command_type = 'builtin'
  AND command_name IN ('so', 'condemn', 'marker', 'winner')
  AND min_role = 'everyone';
