# Niibot API

FastAPI 後端，提供認證、頻道管理、分析等 API。部署於 Render (Docker)。

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

### 頻道 `/api/channels`
- `GET /twitch/monitored` — 監控頻道列表
- `GET /twitch/my-status` — 我的頻道狀態
- `POST /twitch/toggle` — 切換 Bot 狀態

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
- `GET /api/commands/components` — Bot 組件列表
- `GET /health` — 健康檢查
