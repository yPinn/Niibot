# Niibot

多平台直播整合 Bot — Twitch / Discord / Web Dashboard。

## 架構

| 服務 | 技術 | 部署 | Port |
|------|------|------|------|
| API Server | FastAPI + asyncpg | Render (Docker) | 8000 |
| Twitch Bot | TwitchIO 3 | Render (Docker) | 4344 |
| Discord Bot | discord.py 2 | Render (Docker) | 8080 |
| Frontend | React 19 + Vite | Cloudflare Pages | — |

```
backend/
├── api/          # FastAPI — 認證、頻道管理、分析
├── twitch/       # Twitch Bot — 聊天指令、Channel Points、EventSub
├── discord/      # Discord Bot — Slash Commands、管理功能
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

Docker：

```bash
docker compose up -d
```

## 環境變數

各服務皆有 `.env.example`，複製為 `.env` 並填入設定。

## License

MIT
