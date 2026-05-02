# Niibot

多平台直播整合系統，包含 Twitch Bot、Discord Bot 與 Web Dashboard。

## 架構

```text
Niibot/
├── backend/
│   ├── api/        # FastAPI — JWT 認證、Dashboard API
│   ├── twitch/     # TwitchIO 3 Bot
│   ├── discord/    # discord.py 2 Bot
│   ├── shared/     # 共用 DB、Cache、Repositories、Migrations
│   └── scripts/    # DB 管理工具
├── frontend/       # React 19 + Vite + Tailwind CSS v4
│   └── functions/  # Cloudflare Pages Functions（API 反向代理）
└── data/           # 靜態資料（運勢、塔羅、遊戲等 JSON）
```

| 服務        | 技術              | 部署             |
| ----------- | ----------------- | ---------------- |
| API         | FastAPI + asyncpg | Docker           |
| Twitch Bot  | TwitchIO 3        | Docker           |
| Discord Bot | discord.py 2      | Docker           |
| Database    | PostgreSQL 16     | Docker           |
| Frontend    | React 19 + Vite   | Cloudflare Pages |

後端透過 **Cloudflare Tunnel** 對外；前端部署在 **Cloudflare Pages**，`/api/*` 由 CF Pages Functions 代理至後端。

## 快速開始

```bash
# 複製所有 .env 範本
cp .env.example .env
cp backend/shared.env.example backend/shared.env
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
cp backend/scrapling/.env.example backend/scrapling/.env
```

> 本機開發可建立 `backend/shared.env.local`（gitignored）覆蓋 `shared.env` 中的值。

```bash
# 本機開發
cd backend && uv sync --group dev
uv run python api/main.py      # API :8000
uv run python twitch/main.py   # Twitch Bot
uv run python discord/bot.py   # Discord Bot

cd frontend && npm install && npm run dev

# 生產部署
docker compose build && docker compose up -d
```

啟動時 `migrate` 容器自動執行 DB Migration。

CI/CD 密鑰（GitHub Actions 部署前執行一次）：

```bash
cp secrets.env.example secrets.env
cp variables.env.example variables.env
bash scripts/push-secrets.sh
```

## 環境變數

| 檔案                     | 內容                                                                   |
| ------------------------ | ---------------------------------------------------------------------- |
| `.env`                   | PostgreSQL 帳號、Cloudflare Tunnel Token                               |
| `backend/shared.env`     | DB URL、Frontend URL、Twitch App 金鑰、Groq / Gemini / OpenRouter、YouTube API Key |
| `backend/api/.env`       | JWT Secret、API URL                                                    |
| `backend/twitch/.env`    | Bot ID、Owner ID                                                       |
| `backend/discord/.env`   | Discord Bot Token、Presence 設定                                       |
| `backend/scrapling/.env` | Threads / Instagram session cookie                                     |

Cloudflare Pages 需設定環境變數 `API_BACKEND`（後端位址）。

## 外部服務

| 服務                                                       | 用途                        |
| ---------------------------------------------------------- | --------------------------- |
| [Twitch Developer Console](https://dev.twitch.tv/console)  | OAuth CLIENT_ID / SECRET    |
| [Discord Developer Portal](https://discord.com/developers) | Bot Token                   |
| [Cloudflare Zero Trust](https://dash.cloudflare.com/)      | Tunnel Token（生產環境）    |
| [OpenRouter](https://openrouter.ai/keys)                   | AI 功能（選用）             |
| [Google Cloud Console](https://console.cloud.google.com/)  | YouTube Data API v3（選用） |

## 測試

```bash
cd backend && uv run pytest tests/ -v
cd frontend && npm run test:coverage
```

## License

MIT
