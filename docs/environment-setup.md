# Niibot 環境變數配置指南

## 概述

Niibot 由多個服務組成,每個服務都有自己的 `.env` 配置文件。本文檔說明如何正確配置這些環境變數。

## 配置文件位置

```
Niibot/
├── backend/
│   ├── api/.env          # API Server 配置
│   ├── twitch/.env       # Twitch Bot 配置
│   └── discord/.env      # Discord Bot 配置
└── frontend/.env         # Frontend 配置
```

## 快速開始

1. 複製所有 `.env.example` 為 `.env`:
```bash
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
cp frontend/.env.example frontend/.env
```

2. 根據下面的配置指南填入實際值

## 共享配置 (需要保持一致)

以下配置需要在多個服務中保持**完全相同的值**:

### 1. Twitch OAuth 憑證

**用於**: API Server + Twitch Bot

```env
# backend/api/.env
CLIENT_ID=your_twitch_client_id
CLIENT_SECRET=your_twitch_client_secret

# backend/twitch/.env
CLIENT_ID=your_twitch_client_id    # ⚠️ 必須與 API 相同
CLIENT_SECRET=your_twitch_client_secret  # ⚠️ 必須與 API 相同
```

**如何獲取**: [Twitch Developer Console](https://dev.twitch.tv/console)

### 2. Database URL (Supabase)

**用於**: API Server + Twitch Bot

```env
# backend/api/.env
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-PROJECT-REF].supabase.co:5432/postgres

# backend/twitch/.env
DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@[YOUR-PROJECT-REF].supabase.co:5432/postgres  # ⚠️ 必須與 API 相同
```

**如何獲取**:
1. 登入 [Supabase Dashboard](https://supabase.com/dashboard)
2. 選擇你的專案
3. 前往 Settings → Database
4. 複製 Connection String (URI)

**注意**: 使用 Supabase 雲端資料庫,無需本地 PostgreSQL

### 3. Frontend URL

**用於**: API Server + Twitch Bot

```env
# backend/api/.env
FRONTEND_URL=http://localhost:3000

# backend/twitch/.env
FRONTEND_URL=http://localhost:3000  # ⚠️ 必須與 API 相同
```

### 4. Log Level

**用於**: 所有服務

```env
# 建議所有服務使用相同的 log level
LOG_LEVEL=INFO
```

## 服務特定配置

### API Server (`backend/api/.env`)

```env
# JWT 認證
JWT_SECRET_KEY=your-secret-key-change-this-in-production
JWT_EXPIRE_DAYS=30

# 服務 URL
API_URL=http://localhost:8000
BOT_URL=http://localhost:4343
```

### Twitch Bot (`backend/twitch/.env`)

```env
# Bot 身份
BOT_ID=your_bot_user_id
OWNER_ID=your_owner_user_id

# EventSub (選填)
# CONDUIT_ID=your_conduit_id
# OAUTH_REDIRECT_URI=https://your-domain.com/oauth/callback

# OpenRouter AI
OPENROUTER_API_KEY=your_openrouter_api_key
OPENROUTER_MODEL=x-ai/grok-4.1-fast:free
```

### Discord Bot (`backend/discord/.env`)

```env
# Discord Bot Token
DISCORD_BOT_TOKEN=your_discord_bot_token

# 測試伺服器 ID (選填,加快指令同步)
# DISCORD_GUILD_ID=your_test_server_id

# Bot 狀態
DISCORD_STATUS=dnd  # online, idle, dnd, invisible
DISCORD_ACTIVITY_TYPE=watching
DISCORD_ACTIVITY_NAME=正在串流中...

# 速率限制
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WARNING_THRESHOLD=0.7
RATE_LIMIT_CRITICAL_THRESHOLD=0.9
```

### Frontend (`frontend/.env`)

```env
# Backend API URL
VITE_API_URL=http://localhost:8000
```

## Docker Compose 環境

使用 Docker Compose 時,請確保:

1. **數據庫連接**: 使用 Supabase 連接字串 (與本地開發相同)
   ```env
   DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres
   ```

2. **服務間通訊**: 使用容器名稱
   ```env
   API_URL=http://api:8000
   BOT_URL=http://twitch-bot:4343
   ```

## 本地開發環境

本地開發時,請使用:

1. **數據庫連接**: 使用 Supabase 連接字串 (與 Docker 相同)
   ```env
   DATABASE_URL=postgresql://postgres:[PASSWORD]@[PROJECT-REF].supabase.co:5432/postgres
   ```

2. **服務 URL**: `localhost` + 對應端口
   ```env
   API_URL=http://localhost:8000
   BOT_URL=http://localhost:4343
   FRONTEND_URL=http://localhost:3000
   ```

## 安全注意事項

### ⚠️ 敏感資訊保護

1. **永遠不要提交 `.env` 到 Git**
   - 已在 `.gitignore` 中排除
   - 只提交 `.env.example` 模板

2. **生產環境必須更改的值**:
   - `JWT_SECRET_KEY`: 使用強隨機密鑰
   - `POSTGRES_PASSWORD`: 使用強密碼
   - 所有 API Keys 和 Tokens

3. **密鑰生成範例**:
   ```bash
   # 生成安全的 JWT Secret
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

## 常見問題

### Q: 為什麼 CLIENT_ID 需要在兩個地方配置?

A: API Server 和 Twitch Bot 都需要訪問 Twitch API,因此都需要 OAuth 憑證。保持分離可以:
- 每個服務獨立運行
- 更好的安全隔離
- 支持不同環境的部署

### Q: 可以合併所有 .env 嗎?

A: 不建議。每個服務應該只知道自己需要的配置,這是最小權限原則。例如:
- Discord Bot 不需要知道 Twitch 憑證
- API Server 不需要知道 Discord Token

### Q: Docker 和本地開發可以用同一個 .env 嗎?

A: 可以! 因為使用 Supabase 雲端資料庫:
- `DATABASE_URL` 在兩種環境都相同 (Supabase 連接字串)
- 只有服務間 URL 需要調整 (容器名稱 vs localhost)

大部分配置可以共用。

## 配置檢查清單

在啟動服務前,請檢查:

- [ ] 所有 `.env.example` 已複製為 `.env`
- [ ] Twitch `CLIENT_ID` 和 `CLIENT_SECRET` 在 API 和 Twitch Bot 中一致
- [ ] `DATABASE_URL` 已設為 Supabase 連接字串 (API 和 Twitch Bot 中一致)
- [ ] `FRONTEND_URL` 在 API 和 Twitch Bot 中一致
- [ ] 生產環境已更改所有預設密鑰和密碼
- [ ] Discord Bot Token 已正確填入
- [ ] 所有必要的 API Keys 已獲取並填入

## 獲取憑證

### Twitch OAuth

1. 訪問 [Twitch Developer Console](https://dev.twitch.tv/console)
2. 創建新應用程式
3. 複製 Client ID 和 Client Secret

### Discord Bot Token

1. 訪問 [Discord Developer Portal](https://discord.com/developers/applications)
2. 創建新應用程式
3. 在 "Bot" 頁面複製 Token

### Supabase Database

1. 訪問 [Supabase Dashboard](https://supabase.com/dashboard)
2. 創建新專案或選擇現有專案
3. 前往 Settings → Database
4. 複製 Connection String (URI)
5. 填入 `DATABASE_URL` (確保 API 和 Twitch Bot 使用相同值)

### OpenRouter API Key

1. 訪問 [OpenRouter](https://openrouter.ai/keys)
2. 創建新 API Key
3. 選擇合適的模型

## 更新日誌

- 2025-12-26: 改用 Supabase 雲端資料庫,移除本地 PostgreSQL
- 2025-12-26: 新增 Discord Bot 速率限制配置
- 初始版本: 基本環境變數配置
