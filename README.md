# Niibot

多平台直播整合 Bot — Twitch / Discord / Web Dashboard。

## 架構

| 服務 | 技術 | 部署 | Port |
| ---- | ---- | ---- | ---- |
| API Server | FastAPI + asyncpg | Docker (Oracle VPS) | 8000 |
| Twitch Bot | TwitchIO 3 | Docker (Oracle VPS) | 4344 |
| Discord Bot | discord.py 2 | Docker (Oracle VPS) | 8080 |
| PostgreSQL | postgres:16 | Docker (Oracle VPS) | 5432 |
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

## 部署（Docker Compose）

所有後端服務與 PostgreSQL 透過 Docker Compose 統一管理。

### 1. 設定環境變數

```bash
# 根目錄：PostgreSQL 帳號（供 docker-compose.yml 使用）
cp .env.example .env

# 各服務
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
```

### 2. 啟動

```bash
docker compose up -d
```

### 3. 初次建立資料表（首次部署）

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

## License

MIT
