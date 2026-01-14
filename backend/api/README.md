# Niibot API

FastAPI 後端服務，管理 Twitch/Discord 機器人。

**版本**: 2.0.0

## 架構

```
backend/api/
├── core/
│   ├── config.py             # Pydantic Settings
│   ├── database.py           # Database Pool
│   ├── logging.py            # Logging
│   └── dependencies.py       # DI
│
├── services/
│   ├── auth_service.py       # JWT Auth
│   ├── twitch_api.py         # Twitch API
│   ├── channel_service.py    # Channel Operations
│   └── analytics_service.py  # Analytics
│
├── routers/
│   ├── auth_router.py        # /api/auth
│   ├── channels_router.py    # /api/channels
│   ├── analytics_router.py   # /api/analytics
│   ├── commands_router.py    # /api/commands
│   ├── stats_router.py       # /api/stats
│   └── bots_router.py        # /api/bots
│
├── app.py                     # App Factory
└── main.py                    # Entry Point
```

## API 端點

### 認證
- `GET /api/auth/twitch/oauth` - OAuth URL
- `GET /api/auth/twitch/callback` - OAuth 回調
- `GET /api/auth/user` - 用戶資訊
- `POST /api/auth/logout` - 登出

### 頻道
- `GET /api/channels/monitored` - 監控頻道
- `GET /api/channels/my-status` - 頻道狀態
- `POST /api/channels/toggle` - 啟用/停用

### 分析
- `GET /api/analytics/summary` - 統計摘要
- `GET /api/analytics/top-commands` - 熱門指令
- `GET /api/analytics/sessions/{id}/commands` - 場次指令
- `GET /api/analytics/sessions/{id}/events` - 場次事件

### Bot 狀態
- `GET /api/bots/twitch/status` - Twitch Bot 狀態
- `GET /api/bots/discord/status` - Discord Bot 狀態

### 文檔
- Swagger UI: http://localhost:8000/docs (開發環境)
- Health Check: http://localhost:8000/api/health

## 啟動

```bash
# 複製環境變數
cp .env.example .env

# 開發模式
python main.py

# 生產模式
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 環境變數

參考 `.env.example`：
- Twitch OAuth (CLIENT_ID, CLIENT_SECRET)
- JWT (JWT_SECRET_KEY)
- Database (DATABASE_URL)
- Bot URLs (TWITCH_BOT_URL, DISCORD_BOT_URL)

## 命名規範

- Router: `*_router.py`
- Service: `*_service.py`
- 類: `<Name>Service`, `<Name>Client`
