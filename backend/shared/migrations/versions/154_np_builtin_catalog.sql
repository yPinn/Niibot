-- 154: !np joins the builtin catalog (it was a runtime-only command).
--
-- Migration 150 only *disabled* legacy custom rows named `np`, because it was a
-- runtime-only name then. Now that `np` is a catalog canonical name, such a row
-- would be returned by the exact-name config lookup instead of the catalog
-- default — a disabled custom row would silently switch !np off for that
-- channel. Move it aside exactly as 150 did for the other catalog names; the
-- response, settings and aliases stay intact for operator recovery.

UPDATE command_configs AS command
SET command_name =
        left('__legacy_' || command.command_name, 30)
        || '_' || command.id::text
        || '_' || substr(md5(command.channel_id || ':' || command.command_name), 1, 8),
    enabled = FALSE
WHERE command.command_type = 'custom'
  AND lower(command.command_name) = 'np';
