# Niibot API Server

獨立的 FastAPI server，專門處理前端請求，與 TwitchIO bot 分離。

## 架構設計

```
backend/
├── api/                    # API server（此目錄）
│   ├── main.py            # FastAPI 主程式
│   ├── routers/           # API 路由模組
│   │   ├── auth.py        # 認證相關路由
│   │   └── ...            # 其他路由
│   └── services/          # 服務層（未來擴展）
└── twitch/                # TwitchIO bot 本體
    ├── main.py
    └── components/
```

## API 路徑結構

### 認證相關 (`/api/auth`)

- `GET /api/auth/twitch/oauth` - 取得 Twitch OAuth URL
- `GET /api/auth/twitch/callback` - Twitch OAuth callback 處理
- `GET /api/auth/discord/oauth` - （未來）Discord OAuth URL
- `GET /api/auth/discord/callback` - （未來）Discord callback

### 其他

- `GET /api/health` - 健康檢查
- `GET /` - API 根路徑資訊
- `GET /docs` - API 文檔（FastAPI 自動生成）

## 啟動方式

```bash
cd backend/api
python main.py
```

服務將運行在 `http://localhost:8000`

## 環境變數

需要的環境變數（從 `backend/twitch/.env` 讀取）：

- `CLIENT_ID` - Twitch Client ID
- `FRONTEND_URL` - 前端 URL（預設: http://localhost:3000）

## 與 TwitchIO Bot 的互動

目前 API server 和 TwitchIO bot 是分離的：

1. **API Server (Port 8000)**: 處理前端請求、OAuth URL 生成
2. **TwitchIO Bot (Port 4343)**: 處理 Twitch 事件、管理 tokens

未來需要實作：
- API server 將 OAuth code 轉發給 bot
- Bot 提供 API 讓 API server 查詢數據

## 擴展性

此架構設計支援多平台：
- 新增平台只需在 `routers/auth.py` 添加對應路由
- 或創建新的 router 檔案（如 `routers/discord.py`）
- 前端透過統一的 `/api/auth/{platform}/*` 格式訪問
