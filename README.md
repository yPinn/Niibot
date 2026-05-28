# Niibot

多平台直播整合系統，包含 Twitch Bot、Discord Bot 與 Web Dashboard。

## 架構

```text
Niibot/
├── backend/
│   ├── api/        # FastAPI — JWT 認證、Dashboard API（16 個 Routers）
│   ├── twitch/     # TwitchIO 3 Bot + EventSub + pg_notify 即時設定重載
│   ├── discord/    # discord.py 2 Bot（Cogs 模組架構）
│   ├── scrapling/  # Instagram / Threads 媒體抓取服務
│   ├── shared/     # 共用 DB、Cache、Repositories、Migrations（67 個）
│   └── scripts/    # DB 管理工具
├── frontend/       # React 19 + Vite + Tailwind CSS v4
│   └── functions/  # Cloudflare Pages Functions（API 反向代理）
└── data/           # 靜態資料（運勢、塔羅、遊戲等 JSON）
```

| 服務        | 技術                    | 部署             |
| ----------- | ----------------------- | ---------------- |
| API         | FastAPI 0.129 + asyncpg | Docker           |
| Twitch Bot  | TwitchIO 3              | Docker           |
| Discord Bot | discord.py 2            | Docker           |
| Scrapling   | Python + scrapling      | Docker           |
| Database    | PostgreSQL 16           | Docker           |
| Frontend    | React 19 + Vite 7       | Cloudflare Pages |

後端透過 **Cloudflare Tunnel** 對外；前端部署在 **Cloudflare Pages**，`/api/*` 由 CF Pages Functions 代理至後端。

各子系統詳細說明：[backend/README.md](backend/README.md) · [frontend/README.md](frontend/README.md)

## 快速開始

```bash
# 複製所有 .env 範本（已存在的檔案會自動略過）
bash scripts/env.sh init

# 或強制覆蓋
bash scripts/env.sh init -f
```

接著填入各檔案的 secrets，再啟動服務：

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
# 從範本建立（僅首次）
cp .github/secrets/base.env.example .github/secrets/base.env
cp .github/secrets/prod.env.example .github/secrets/prod.env
cp .github/secrets/staging.env.example .github/secrets/staging.env
cp .github/variables/base.env.example .github/variables/base.env
cp .github/variables/prod.env.example .github/variables/prod.env
cp .github/variables/staging.env.example .github/variables/staging.env

# 填入值後同步至 GitHub
bash .github/push.sh prod

# 或從 GitHub 拉回現有值
bash .github/pull.sh prod
```

## 環境變數

| 檔案                     | 內容                                                                               |
| ------------------------ | ---------------------------------------------------------------------------------- |
| `.env`                   | PostgreSQL 帳號、Docker 內部 DATABASE_URL                                          |
| `backend/shared.env`     | DB URL、Frontend URL、Twitch App 金鑰、Bot / Owner ID、AI keys、YouTube API Key    |
| `backend/api/.env`       | JWT Secret、API URL、Discord Public Key                                            |
| `backend/twitch/.env`    | Conduit ID（optional）                                                             |
| `backend/discord/.env`   | Discord Bot Token、Presence 設定                                                   |
| `backend/scrapling/.env` | Threads session cookie                                                             |
| `frontend/.env`          | Vite dev proxy、Bot username、Discord invite URL                                   |

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
