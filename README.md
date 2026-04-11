# Niibot

多平台直播整合 Bot — Twitch / Discord / Web Dashboard。

## 架構

| 服務        | 技術              | 部署             | 對外 Port |
| ----------- | ----------------- | ---------------- | --------- |
| API Server  | FastAPI + asyncpg | Docker           | 8000      |
| Twitch Bot  | TwitchIO 3        | Docker           | — 僅內部  |
| Discord Bot | discord.py 2      | Docker           | — 僅內部  |
| PostgreSQL  | postgres:16       | Docker           | — 僅內部  |
| Frontend    | React 19 + Vite   | Cloudflare Pages | —         |

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
cd backend && cp api/.env.example api/.env   # 填入設定
uv sync && uv run python api/main.py

# Frontend（需 Node 20+）
cd frontend && npm install && npm run dev
```

## 部署

### 前端（Cloudflare Pages）

React SPA，部署在 Cloudflare Pages。CF Pages Functions 將 `/api/*`、`/health`、`/status` 代理到後端，瀏覽器全程只與 CF Pages 域名通訊。

在 CF Pages 專案 → 環境變數中設定：

| 變數          | 說明                                         |
| ------------- | -------------------------------------------- |
| `API_BACKEND` | 後端 API 位址（經由 Cloudflare Tunnel 提供） |

### 後端（Docker Compose）

後端服務統一由 Docker Compose 管理。啟動後 `migrate` 容器會自動執行 DB Migration，成功後才啟動其他服務。

生產環境透過 **Cloudflare Tunnel** 對外，cloudflared 作為系統服務運行並指向 `localhost:8000`。

#### 1. 設定環境變數

```bash
cp .env.example .env                                         # PostgreSQL 帳號 + Cloudflare Tunnel Token
cp backend/shared.env.example backend/shared.env            # 共用（DB URL、OpenRouter、YouTube API）
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
```

#### 2. 建置並啟動

```bash
docker compose build
docker compose up -d
```

## 環境變數

| 檔案                      | 說明                                     |
| ------------------------- | ---------------------------------------- |
| `.env`                    | PostgreSQL 帳號、Cloudflare Tunnel Token |
| `backend/shared.env`      | 共用 — DB URL、OpenRouter API、YouTube API |
| `backend/api/.env`        | Twitch OAuth、JWT Secret、服務 URL       |
| `backend/twitch/.env`     | Twitch Bot 金鑰                          |
| `backend/discord/.env`    | Discord Bot Token                        |

### 需準備的外部服務

| 服務                     | 取得位置                                                              | 用途                                |
| ------------------------ | --------------------------------------------------------------------- | ----------------------------------- |
| Twitch Developer Console | [dev.twitch.tv/console](https://dev.twitch.tv/console)                | OAuth CLIENT_ID / CLIENT_SECRET     |
| Discord Developer Portal | [discord.com/developers](https://discord.com/developers/applications) | Bot Token                           |
| Cloudflare Zero Trust    | Cloudflare Dashboard → Networks → Tunnels                             | Tunnel Token（生產環境）            |
| OpenRouter               | [openrouter.ai/keys](https://openrouter.ai/keys)                      | OPENROUTER_API_KEY（選用，AI 功能） |
| YouTube Data API v3      | [console.cloud.google.com](https://console.cloud.google.com/)         | YOUTUBE_API_KEY（選用）             |

## License

MIT
