# Niibot API

FastAPI 後端服務，管理 Twitch/Discord 機器人。

**版本**: 2.0.0
**架構**: FastAPI + Dependency Injection

## 架構概覽

```
backend/api/
├── core/                      # 核心模組
│   ├── config.py             # Pydantic Settings
│   ├── database.py           # 資料庫連接池
│   ├── logging.py            # 日誌配置
│   └── dependencies.py       # 依賴注入
│
├── services/                  # 業務邏輯層
│   ├── auth_service.py       # JWT 認證
│   ├── twitch_api.py         # Twitch API
│   ├── channel_service.py    # 頻道操作
│   └── analytics_service.py  # 分析統計
│
├── routers/                   # API 路由層
│   ├── auth_router.py        # 認證端點
│   ├── channels_router.py    # 頻道管理
│   ├── analytics_router.py   # 分析統計
│   ├── commands.py           # 指令查詢
│   └── stats.py              # 統計資料
│
├── app.py                     # App Factory
└── main.py                    # 應用入口
```

## API 文檔

- **Complete API Reference**: [/docs/API_ENDPOINTS.md](../../docs/API_ENDPOINTS.md)
- Swagger UI: http://localhost:8000/docs (development only)
- ReDoc: http://localhost:8000/redoc (development only)
- Health Check: http://localhost:8000/api/health

## 主要端點

完整端點列表請參考 [API Endpoints Reference](../../docs/API_ENDPOINTS.md)

### 認證 (Authentication)
- `GET /api/auth/twitch/oauth` - 獲取 OAuth URL
- `GET /api/auth/twitch/callback` - OAuth 回調
- `GET /api/auth/user` - 獲取用戶信息
- `POST /api/auth/logout` - 用戶登出

### 頻道管理 (Channels)
- `GET /api/channels/monitored` - 監控頻道列表
- `GET /api/channels/my-status` - 我的頻道狀態
- `POST /api/channels/toggle` - 啟用/停用機器人

### 分析統計 (Analytics)
- `GET /api/analytics/summary` - 統計摘要
- `GET /api/analytics/top-commands` - 熱門指令
- `GET /api/analytics/sessions/{id}/commands` - 場次指令
- `GET /api/analytics/sessions/{id}/events` - 場次事件

## 快速開始

### 配置環境變數

```env
# Twitch OAuth
CLIENT_ID=your_twitch_client_id
CLIENT_SECRET=your_twitch_client_secret

# JWT
JWT_SECRET_KEY=your_jwt_secret_key

# Database
DATABASE_URL=postgresql://user:pass@localhost:5432/niibot

# URLs
FRONTEND_URL=http://localhost:3000
API_URL=http://localhost:8000
BOT_URL=http://localhost:4343

# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO
```

### 啟動服務

```bash
cd backend/api

# 開發模式（自動重載）
python main.py

# 或使用 uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 生產模式
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## 設計模式

### Dependency Injection
```python
from fastapi import Depends
from core.dependencies import get_current_user_id

@router.get("/protected")
async def protected_route(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}
```

### Service Layer
```python
class AuthService:
    def create_access_token(self, user_id: str) -> str:
        ...
```

## 命名規範

- 服務: `<domain>_service.py`
- 路由: `<domain>_router.py`
- 類: `<Name>Service`, `<Name>Client`, `<Name>Manager`
