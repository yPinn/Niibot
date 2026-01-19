# Niibot API

FastAPI 後端服務。

## 啟動

```bash
cp .env.example .env
python main.py
```

## API 端點

### 認證 `/api/auth`
- `GET /twitch/oauth` - OAuth URL
- `GET /twitch/callback` - OAuth 回調
- `GET /discord/oauth` - Discord OAuth URL
- `GET /discord/callback` - Discord OAuth 回調
- `GET /user` - 當前用戶
- `POST /logout` - 登出

### 頻道 `/api/channels`
- `GET /twitch/monitored` - 監控頻道列表
- `GET /twitch/my-status` - 我的頻道狀態
- `POST /twitch/toggle` - 切換 Bot 狀態

### Bot 狀態 `/api/bots`
- `GET /twitch/status` - Twitch Bot 狀態
- `GET /discord/status` - Discord Bot 狀態

### 其他
- `GET /api/analytics/*` - 分析數據
- `GET /api/commands/components` - Bot 組件列表
- `GET /api/health` - 健康檢查
