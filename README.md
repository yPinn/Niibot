# Niibot

多平台直播整合 Bot — Twitch / Discord / Web Dashboard。

## 架構

| 服務 | 技術 | 部署 | 對外 Port |
| ---- | ---- | ---- | ---- |
| API Server | FastAPI + asyncpg | Docker (Oracle VPS) | 8000 |
| Twitch Bot | TwitchIO 3 | Docker (Oracle VPS) | — 僅內部 |
| Discord Bot | discord.py 2 | Docker (Oracle VPS) | — 僅內部 |
| PostgreSQL | postgres:16 | Docker (Oracle VPS) | — 僅內部 |
| Frontend | React 19 + Vite | Cloudflare Pages | — |

```text
backend/
├── api/          # FastAPI — 認證、頻道管理、指令/事件設定
├── twitch/       # Twitch Bot — 聊天指令、Channel Points、EventSub
├── discord/      # Discord Bot — Slash Commands、管理功能
├── shared/       # 共用模組 — DB、Cache、Models、Repositories、Migrations
├── scripts/      # 工具腳本 — DB 管理、OAuth、Discord 資源
├── data/         # 靜態資料 — 運勢、塔羅、遊戲等 JSON
├── pyproject.toml
└── uv.lock
frontend/
├── src/          # React SPA
├── functions/    # CF Pages Functions（API 反向代理）
└── public/
```

## 開發

```bash
# Backend（需 Python 3.11+、uv）
cd backend && cp api/.env.example api/.env
uv sync && uv run python api/main.py

# Frontend（需 Node 20+）
cd frontend && cp .env.example .env
npm install && npm run dev
```

## 部署

### 前端（Cloudflare Pages）

前端為 React SPA，部署在 Cloudflare Pages；CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到 VPS API，瀏覽器全程只與 CF Pages 域名通訊。

在 CF Pages 專案設定 → 環境變數：

| 變數 | 說明 |
| ---- | ---- |
| `API_BACKEND` | VPS API 位址，例如 `http://your-vps-ip:8000` |

### 後端（Oracle VPS — Docker Compose）

後端服務（API、Twitch Bot、Discord Bot、PostgreSQL）統一透過 Docker Compose 管理。VPS 上只需對外開放 **port 8000**（API，供 CF Functions 呼叫）。

#### 1. 設定環境變數

```bash
# 根目錄：PostgreSQL 帳號（供 docker-compose.yml 使用）
cp .env.example .env

# 各服務
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
```

#### 2. 啟動

```bash
docker compose up -d
```

#### 3. 初次建立資料表（首次部署）

```bash
docker compose run --rm \
  -v ./backend/scripts:/app/scripts \
  api python /app/scripts/db_migrate.py
```

## 環境變數

各服務皆有 `.env.example`，複製為 `.env` 並填入設定。

| 檔案 | 說明 |
| ---- | ---- |
| `.env` | PostgreSQL 帳號（`POSTGRES_USER/PASSWORD/DB`） |
| `backend/api/.env` | Twitch OAuth、JWT、服務 URL |
| `backend/twitch/.env` | Twitch Bot 金鑰、YouTube API |
| `backend/discord/.env` | Discord Bot Token |

### 需準備的外部服務

| 服務 | 取得位置 | 用途 |
| ---- | -------- | ---- |
| Twitch Developer Console | [dev.twitch.tv/console](https://dev.twitch.tv/console) | CLIENT_ID / CLIENT_SECRET |
| Discord Developer Portal | [discord.com/developers](https://discord.com/developers/applications) | Bot Token、OAuth CLIENT_ID / CLIENT_SECRET |
| OpenRouter | [openrouter.ai/keys](https://openrouter.ai/keys) | OPENROUTER_API_KEY |
| YouTube Data API v3 | [console.cloud.google.com](https://console.cloud.google.com/) | YOUTUBE_API_KEY（選用） |

## License

MIT
