-- 150: Fail closed for legacy custom commands that shadow the unified command namespace.
--
-- New writes are rejected by the API and chat manager, and the runtime also
-- bypasses reserved names before querying custom commands.  This migration
-- handles rows created before those guards existed.  A custom row occupying a
-- catalog canonical name must also move aside, otherwise the unique constraint
-- prevents the real builtin row (and even the virtual catalog fallback) from
-- appearing.  The deterministic legacy name remains visible in Commands;
-- responses, settings and aliases stay intact for operator recovery.

WITH builtin(name) AS (
    VALUES
        ('accountage'),
        ('bits'),
        ('checkin'),
        ('choose'),
        ('condemn'),
        ('crosshairs'),
        ('del'),
        ('followage'),
        ('fortune'),
        ('game'),
        ('help'),
        ('marker'),
        ('ping'),
        ('quote'),
        ('rank'),
        ('roll'),
        ('schedule'),
        ('so'),
        ('subage'),
        ('subcount'),
        ('tags'),
        ('tarot'),
        ('tft'),
        ('title'),
        ('uptime'),
        ('winner')
)
UPDATE command_configs AS command
SET command_name =
        left('__legacy_' || command.command_name, 30)
        || '_' || command.id::text
        || '_' || substr(md5(command.channel_id || ':' || command.command_name), 1, 8),
    enabled = FALSE
WHERE command.command_type = 'custom'
  AND EXISTS (
      SELECT 1
      FROM builtin
      WHERE builtin.name = lower(command.command_name)
  );

WITH reserved(name) AS (
    VALUES
        ('accountage'),
        ('ai'),
        ('alive'),
        ('bits'),
        ('checkin'),
        ('choose'),
        ('cmd'),
        ('commands'),
        ('comp'),
        ('condemn'),
        ('crosshairs'),
        ('del'),
        ('followage'),
        ('fortune'),
        ('game'),
        ('gq'),
        ('help'),
        ('marker'),
        ('np'),
        ('ovltest'),
        ('ping'),
        ('quote'),
        ('rank'),
        ('roll'),
        ('schedule'),
        ('so'),
        ('subage'),
        ('subcount'),
        ('tags'),
        ('tarot'),
        ('tft'),
        ('title'),
        ('uptime'),
        ('vanish'),
        ('vq'),
        ('winner'),
        ('xhc'),
        ('下次開台'),
        ('分類'),
        ('刪除'),
        ('台標'),
        ('問'),
        ('塔羅'),
        ('小奇點'),
        ('帳號年齡'),
        ('幸運兒'),
        ('影片'),
        ('戰棋'),
        ('推薦'),
        ('排程'),
        ('斥責'),
        ('標籤'),
        ('標記'),
        ('準星'),
        ('簽到'),
        ('訂閱數'),
        ('訂閱資訊'),
        ('語錄'),
        ('追隨時間'),
        ('運勢'),
        ('選擇'),
        ('輪盤'),
        ('開播時間'),
        ('排名'),
        ('指令')
)
UPDATE command_configs AS command
SET enabled = FALSE
WHERE command.command_type = 'custom'
  AND command.enabled = TRUE
  AND (
      EXISTS (
          SELECT 1
          FROM reserved
          WHERE reserved.name = lower(command.command_name)
      )
      OR EXISTS (
          SELECT 1
          FROM command_aliases AS alias
          JOIN reserved ON reserved.name = lower(alias.alias)
          WHERE alias.command_id = command.id
      )
  );
