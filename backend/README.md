# Backend

Python 後端，三個服務共用 `shared/` 模組。詳細部署說明見根目錄 [README](../README.md)。

## 結構

```text
backend/
├── api/        # FastAPI — Twitch OAuth + JWT、頻道/指令/事件/贊助 API
├── twitch/     # Twitch Bot — 聊天指令、VideoQueue、GameQueue、Channel Points、EventSub
├── discord/    # Discord Bot — Slash Commands、生日提醒、社群預覽、AI
├── shared/     # 共用模組（詳見下方）
├── scripts/    # DB 管理、OAuth token 工具
├── data/       # 靜態 JSON（運勢、塔羅、遊戲清單等）
├── tests/      # pytest
├── pyproject.toml
└── uv.lock
```

### shared/ 模組

| 模組                    | 說明                                                           |
| ----------------------- | -------------------------------------------------------------- |
| `database.py`           | asyncpg 連線池管理、`pool_heartbeat_loop`                      |
| `cache.py`              | `AsyncTTLCache`（LRU + TTL）；搭配 `pg_notify` 即時失效        |
| `config_base.py`        | `BaseServiceSettings`：三服務共用 config 基底                  |
| `health_server_base.py` | `BaseHealthServer`：Discord / Twitch health server 基底        |
| `logging_setup.py`      | 結構化 logging 設定（含 Discord webhook error handler）        |
| `builtin_commands.py`   | 內建指令定義與別名映射                                         |
| `ai_provider.py`        | 多 AI Provider 鏈（Groq / Gemini / OpenRouter），自動 fallback |
| `models/`               | Pydantic 資料模型                                              |
| `repositories/`         | 資料庫存取層（per-domain）                                     |
| `migrations/`           | 自製 migration runner；版本腳本在 `versions/`（目前 v040）     |

## 服務架構

```text
Frontend ──HTTP──▶ API (8000)
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     PostgreSQL  Twitch Bot  Discord Bot
      (shared)   health:4344  health:8080
```

- **快取**：`AsyncTTLCache`（程序內）+ `pg_notify`（跨程序即時失效）
- **錯誤告警**：ERROR 以上 log 推送至 Discord webhook

| 服務                 | Port   |
| -------------------- | ------ |
| API                  | `8000` |
| Discord Bot health   | `8080` |
| Twitch Bot health    | `4344` |
| Scrapling sidecar    | `3001` |
| PostgreSQL（Docker） | `5433` |

## 開發

```bash
cd backend
uv sync
uv run python api/main.py      # API
uv run python twitch/main.py   # Twitch Bot
uv run python discord/bot.py   # Discord Bot

uv run pytest              # 測試
uv run ruff check .        # Lint
uv run ruff format .       # 格式化
uv run mypy .              # 型別檢查
```

## 環境變數

```bash
cp shared.env.example shared.env
cp api/.env.example api/.env
cp twitch/.env.example twitch/.env
cp discord/.env.example discord/.env
```

> 本機開發可建立 `shared.env.local`（gitignored）覆蓋 `shared.env`。`TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` 三服務共用，無需在 `api/.env` 重複設定。

| 檔案             | 說明                                                                               |
| ---------------- | ---------------------------------------------------------------------------------- |
| `shared.env`     | DB URL、Frontend URL、Twitch App 金鑰、Groq / Gemini / OpenRouter、YouTube API Key |
| `api/.env`       | JWT Secret、API URL                                                                |
| `twitch/.env`    | Bot ID、Owner ID、EventSub 設定                                                    |
| `discord/.env`   | Discord Bot Token、Presence 設定                                                   |
| `scrapling/.env` | Threads / Instagram session cookie                                                 |

## DB Migrations

```bash
# 開發用（Docker 環境下由 migrate 容器自動執行）
uv run python scripts/db_migrate.py
```

## API 端點

開發環境互動式文件：`http://localhost:8000/docs`

| 路由前綴               | 功能                                                  |
| ---------------------- | ----------------------------------------------------- |
| `/api/auth`            | Twitch OAuth、JWT cookie、用戶偏好                    |
| `/api/channels`        | 監控頻道管理、Bot 啟停                                |
| `/api/commands`        | 指令 CRUD、啟停、公開列表                             |
| `/api/events`          | EventSub 事件設定、Channel Points 兌換                |
| `/api/analytics`       | 場次分析、觀眾 Profile、熱門指令統計                  |
| `/api/stats/channel`   | 頻道統計（top chatters / commands）                   |
| `/api/game-queue`      | 遊戲排隊                                              |
| `/api/video-queue`     | 影片佇列                                              |
| `/api/timers`          | 定時訊息 CRUD                                         |
| `/api/triggers`        | 關鍵字觸發 CRUD                                       |
| `/api/donate`          | 贊助結帳（ECPay / OPay / NewebPay / PayPal）、webhook |
| `/api/payment-configs` | 金流平台設定                                          |
| `/api/bots`            | Bot 狀態查詢                                          |
| `/health`, `/status`   | 服務健康檢查                                          |

**安全機制：** JWT httponly cookie（HS256、30 天）/ HMAC-SHA256 OAuth CSRF state / 全域安全標頭（CSP、HSTS 等）/ 金流 webhook 驗簽（CheckMacValue SHA-256、NewebPay AES-256-CBC + TradeSha）
