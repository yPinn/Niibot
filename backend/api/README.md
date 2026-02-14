# Niibot API

FastAPI 後端，提供認證、頻道管理、指令/事件設定等 API。部署於 Render (Docker)。

## 啟動

```bash
cp .env.example .env
uv sync && uv run python main.py
```

## API 端點

### 認證 `/api/auth`
- `GET /twitch/oauth` — Twitch OAuth URL
- `GET /twitch/callback` — OAuth 回調
- `GET /discord/status` — Discord OAuth 是否啟用
- `GET /discord/oauth` — Discord OAuth URL
- `GET /discord/callback` — Discord OAuth 回調
- `GET /user` — 當前用戶（需認證）
- `POST /logout` — 登出
- `PATCH /api/user/preferences` — 更新用戶偏好

### 頻道 `/api/channels`
- `GET /twitch/monitored` — 監控頻道列表
- `GET /twitch/my-status` — 我的頻道狀態
- `POST /twitch/toggle` — 切換 Bot 狀態
- `GET /defaults` — 頻道預設冷卻設定
- `PUT /defaults` — 更新頻道預設冷卻設定

### 指令設定 `/api/commands`
- `GET /configs` — 取得所有指令設定
- `POST /configs` — 新增自訂指令
- `PUT /configs/{command_name}` — 更新指令設定
- `PATCH /configs/{command_name}/toggle` — 切換指令啟用狀態
- `DELETE /configs/{command_name}` — 刪除自訂指令
- `GET /public/{username}` — 取得頻道公開指令列表

### 事件設定 `/api/events`
- `GET /configs` — 取得事件設定
- `PUT /configs/{event_type}` — 更新事件設定
- `PATCH /configs/{event_type}/toggle` — 切換事件啟用狀態
- `GET /twitch-rewards` — 取得 Twitch 自訂獎勵
- `GET /redemptions` — 取得兌換設定
- `PUT /redemptions/{action_type}` — 更新兌換設定

### 分析 `/api/analytics`
- `GET /summary` — 總覽（`?days=`）
- `GET /sessions/{id}/commands` — 場次指令統計
- `GET /sessions/{id}/events` — 場次事件
- `GET /top-commands` — 熱門指令（`?days=&limit=`）

### Bot 狀態 `/api/bots`
- `GET /twitch/status` — Twitch Bot 狀態
- `GET /twitch/health` — Twitch Bot 健康檢查
- `GET /discord/status` — Discord Bot 狀態
- `GET /discord/health` — Discord Bot 健康檢查

### 其他
- `GET /api/stats/channel` — 頻道統計
- `GET /health` — 健康檢查
- `GET /status` — 詳細狀態（含 DB）
