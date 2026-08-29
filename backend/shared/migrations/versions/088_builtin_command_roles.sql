-- 088: gate !so and !condemn to moderators by default.
--
-- ## Why
-- `_make_virtual` now reads `min_role` from BUILTIN_DEFS, and both `so` and
-- `condemn` are declared `min_role = "moderator"`. But channels that already
-- toggled either command on have a real `command_configs` row whose `min_role`
-- was written as `'everyone'` by upsert_config's INSERT (COALESCE($7,'everyone')).
-- The virtual-default change does not touch those rows, and `!so` just lost its
-- hard-coded `ctx.chatter.moderator` gate in the handler — so without this,
-- everyone on those channels could run `!so` / `!condemn`.
--
-- Only rows still at the default 'everyone' are bumped; a channel that
-- deliberately set a different role keeps it. A channel that deliberately set
-- 'everyone' is rare and can change it back from the dashboard.

UPDATE command_configs
SET min_role = 'moderator'
WHERE command_name IN ('so', 'condemn')
  AND command_type = 'builtin'
  AND min_role = 'everyone';
