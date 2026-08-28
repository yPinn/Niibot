# Niibot

多平台直播整合系統，包含 Twitch Bot、Discord Bot 與 Web Dashboard。

## 架構

```text
Niibot/
├── backend/
│   ├── api/         # FastAPI — Twitch OAuth + JWT、Dashboard API
│   ├── twitch/      # TwitchIO 3 Bot + EventSub + pg_notify 即時設定重載
│   ├── discord/     # discord.py 2 Bot（Cogs 模組架構）
│   ├── scrapling/   # 選用：Threads 抓取 sidecar（不在 docker-compose）
│   ├── shared/      # 共用 DB、Cache、Repositories、Migrations
│   ├── scripts/     # DB 管理、OAuth token 工具
│   └── data/        # 靜態資料（運勢、塔羅、AI 知識包等）
├── frontend/        # React 19 + Vite + Tailwind CSS 4
│   └── functions/   # Cloudflare Pages Functions（/api 反向代理）
├── docs/            # 架構、操作指南、參考文件
├── scripts/         # env 檔管理、staging 管理
└── data/            # 本機 Docker volume 與備份（不提交）
```

| 服務        | 技術          | 部署             |
| ----------- | ------------- | ---------------- |
| API         | FastAPI       | Docker           |
| Twitch Bot  | TwitchIO 3    | Docker           |
| Discord Bot | discord.py 2  | Docker           |
| Database    | PostgreSQL 16 | Docker           |
| Frontend    | React 19      | Cloudflare Pages |

精確套件版本見 `backend/pyproject.toml` 與 `frontend/package.json`。

後端透過 **Cloudflare Tunnel** 對外；前端部署在 **Cloudflare Pages**，
`/api/*` 由 Pages Functions 代理至後端。

## 快速開始

```bash
bash scripts/env.sh init      # 複製所有 .env 範本（-f 強制覆蓋）
```

填入各檔 secrets 後即可啟動。完整步驟（直接跑程序或走 Docker Compose）見
[docs/guides/development.md](docs/guides/development.md)。

env 變數的單一來源是 [`env.registry.toml`](env.registry.toml)；改動後跑 `npm run env:gen`。

## 文件

| 主題                            | 位置                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------- |
| 文件總覽                        | [docs/README.md](docs/README.md)                                                  |
| 架構總覽 · 多租戶模型           | [docs/architecture/](docs/architecture/)                                          |
| 本機開發 · 部署 · 環境變數      | [docs/guides/](docs/guides/)                                                      |
| API 端點 · 靜態資料 · 版本規範  | [docs/reference/](docs/reference/)                                                |
| Instafix · FixTweet · Scrapling | [docs/integrations/](docs/integrations/)                                          |
| 子系統細節                      | [backend/README.md](backend/README.md) · [frontend/README.md](frontend/README.md) |

## 外部服務

| 服務                                                       | 用途                        |
| ---------------------------------------------------------- | --------------------------- |
| [Twitch Developer Console](https://dev.twitch.tv/console)  | OAuth Client ID / Secret    |
| [Discord Developer Portal](https://discord.com/developers) | Bot Token、互動 Public Key  |
| [Cloudflare Zero Trust](https://dash.cloudflare.com/)      | Tunnel Token（生產環境）    |
| Groq · Gemini · OpenRouter                                 | AI 功能（至少設一組）       |
| [Google Cloud Console](https://console.cloud.google.com/)  | YouTube Data API v3（選用） |

## 測試

```bash
npm run test                     # 前後端一起（vitest --run + pytest）
cd frontend && npm run test:cov  # 只跑前端 + 覆蓋率
cd backend  && uv run pytest     # 只跑後端
```

## License

MIT
