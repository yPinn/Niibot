# Niibot

多平台直播整合系統，包含 Twitch Bot、Discord Bot 與 Web Dashboard。

## 目錄

- [功能概覽](#功能概覽)
- [架構](#架構)
- [快速開始](#快速開始)
- [環境變數](#環境變數)
- [外部服務](#外部服務)
- [測試](#測試)

---

## 功能概覽

### Twitch Bot

- **指令系統** — 自訂指令（`!cmd`）、別名、冷卻、權限分級
- **訊息觸發** — 關鍵字自動回應（contains / startswith / exact / regex，含 ReDoS 防護）
- **計時器** — 排程廣播訊息
- **Channel Points** — 自訂兌換獎勵處理
- **Events** — EventSub 事件回應（上線、訂閱、Raid 等）
- **遊戲隊列** — 排隊管理（GameQueue / VideoQueue）
- **占卜娛樂** — 每日運勢、塔羅牌
- **TFT 戰棋** — 玩家段位查詢與排行榜門檻
- **AI 對話** — 整合 OpenRouter API

### Discord Bot

- **社群預覽** — Instagram、Bilibili、TikTok 連結自動展開嵌入
- **生日追蹤** — 記錄、提醒、訂閱通知
- **抽獎系統** — Giveaway 管理
- **吃什麼** — 隨機餐點推薦與分類瀏覽
- **占卜娛樂** — 每日運勢、塔羅牌
- **TFT 戰棋** — 玩家段位查詢與排行榜門檻
- **伺服器日誌** — 成員進出事件記錄
- **工具指令** — 通用、遊戲、管理、審核
- **AI 對話** — 整合 OpenRouter API

### Web Dashboard

- 指令與觸發詞的 CRUD 管理
- 計時器、VideoQueue、GameQueue 設定
- EventSub 事件設定
- 系統狀態監控

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

後端透過 **Cloudflare Tunnel** 對外，前端部署在 **Cloudflare Pages**，CF Pages Functions 將 `/api/*` 代理至後端，瀏覽器只與 CF Pages 域名通訊。

## 快速開始

### 環境需求

- Python 3.11+、[uv](https://docs.astral.sh/uv/)
- Node.js 20+
- Docker & Docker Compose

### 設定環境變數

```bash
cp .env.example .env
cp backend/shared.env.example backend/shared.env
cp backend/api/.env.example backend/api/.env
cp backend/twitch/.env.example backend/twitch/.env
cp backend/discord/.env.example backend/discord/.env
```

### 本機開發

```bash
# Backend
cd backend
uv sync --group dev
uv run python api/main.py      # API Server
uv run python twitch/main.py   # Twitch Bot
uv run python discord/bot.py   # Discord Bot

# Frontend
cd frontend
npm install
npm run dev
```

### 生產部署（Docker Compose）

```bash
docker compose build
docker compose up -d
```

啟動時 `migrate` 容器會自動執行 DB Migration，成功後其他服務才會啟動。

## 環境變數

| 檔案                   | 內容                                        |
| ---------------------- | ------------------------------------------- |
| `.env`                 | PostgreSQL 帳號、Cloudflare Tunnel Token    |
| `backend/shared.env`   | DB URL、OpenRouter API Key、YouTube API Key |
| `backend/api/.env`     | Twitch OAuth、JWT Secret、服務 URL          |
| `backend/twitch/.env`  | Twitch Bot 金鑰                             |
| `backend/discord/.env` | Discord Bot Token                           |

Cloudflare Pages 專案需設定環境變數 `API_BACKEND`（後端位址）。

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
# Backend
cd backend
uv run pytest tests/ -v

# Frontend
cd frontend
npm run test:coverage
```

## License

MIT
