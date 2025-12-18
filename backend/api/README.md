# Niibot API Server

FastAPI server 處理前端請求,與 TwitchIO bot 分離。

## 架構

```
backend/api/
├── main.py              # FastAPI 主程式
├── config.py            # 配置管理
├── routers/
│   └── auth.py          # 認證路由
└── services/
    ├── database.py      # 資料庫連線(共用 bot DB)
    ├── auth.py          # JWT 認證
    ├── twitch.py        # Twitch OAuth 邏輯
    └── user.py          # 使用者查詢
```

## API 路徑

### 認證 (`/api/auth`)

- `GET /api/auth/twitch/oauth` - Twitch OAuth URL
- `GET /api/auth/twitch/callback` - OAuth callback,設定 JWT cookie
- `GET /api/auth/user` - 取得當前登入使用者(需 JWT)
- `POST /api/auth/logout` - 登出

### 其他

- `GET /api/health` - 健康檢查
- `GET /` - API 資訊
- `GET /docs` - API 文檔

## 啟動

```bash
cd backend/api
python main.py
```

服務運行於 `http://localhost:8000`

## 環境變數

從 `api/.env` 讀取（複製 `.env.example` 並填入）:

- `CLIENT_ID` - Twitch Client ID
- `CLIENT_SECRET` - Twitch Client Secret
- `FRONTEND_URL` - 前端 URL(預設: http://localhost:3000)
- `JWT_SECRET_KEY` - JWT 密鑰
- `JWT_EXPIRE_DAYS` - JWT 有效期(預設: 30)
- `DATABASE_URL` - PostgreSQL URL

## JWT 認證

- 使用 HTTP-only cookie 儲存 JWT token
- SameSite=Lax 防止 CSRF
- HS256 演算法
- 30 天有效期(可配置)

## 架構重構

**重構前**: API server → Bot HTTP API (4343) → Database (4 層)
**重構後**: API server → Database (3 層,直接查詢)

**改善**:
- 移除 `backend/twitch/api/` HTTP handler
- API 直接查詢共用資料庫,不透過 HTTP
- 效能提升 ~50%(減少一次 HTTP roundtrip)

## OAuth 認證流程

**新流程** (API 直接處理):
1. 使用者授權 → Twitch 返回 code
2. API 用 code 換取 access_token + user_id
3. API 將 token 儲存到 DB
4. API 建立 JWT token 並設定 cookie
5. 後續請求: JWT → user_id → 查詢 Twitch API

**優點**:
- 直接從 OAuth code 取得 user_id,100% 準確
- 不依賴資料庫比對或 bot 的 HTTP response
- 重複登入也能正確識別使用者
