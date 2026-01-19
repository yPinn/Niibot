# Database Migrations

執行 migration：

```bash
psql $DATABASE_URL -f 001_add_game_info.sql
```

## Migration 記錄

- `001_add_game_info.sql` - 新增 `game_id` 欄位到 `stream_sessions` 表
