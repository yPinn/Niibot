# Backend

Python 後端，包含 API Server、Twitch Bot、Discord Bot 三個服務，共用 `shared/` 模組。

授權：見根目錄 [LICENSE](../LICENSE)

## 目錄

- [結構](#結構)
- [服務架構](#服務架構)
- [技術棧](#技術棧)
- [前置需求](#前置需求)
- [開發](#開發)
- [指令](#指令)
- [環境變數](#環境變數)
- [DB Migrations](#db-migrations)
- [API 端點](#api-端點)
- [Twitch Bot 指令](#twitch-bot-指令)
- [Twitch EventSub 事件](#twitch-eventsub-事件)
- [Discord Bot 指令](#discord-bot-指令)
- [Discord 伺服器事件日誌](#discord-伺服器事件日誌)

---

## 結構

```text
backend/
├── api/        # FastAPI — 認證（Twitch OAuth + JWT）、頻道管理、指令/事件/排隊/贊助設定
├── twitch/     # Twitch Bot — 聊天指令、影片佇列、遊戲排隊、Channel Points、EventSub
├── discord/    # Discord Bot — Slash Commands、事件日誌、生日提醒、社群預覽、AI 功能
├── shared/     # 共用模組（詳見下方）
├── scripts/    # 工具腳本 — DB 管理、OAuth token 取得、Discord 資源
├── data/       # 靜態 JSON 資料（運勢、塔羅、遊戲清單等）
├── tests/      # pytest 測試（api / twitch / discord / shared）
├── pyproject.toml
└── uv.lock
```

### shared/ 模組

| 模組                         | 說明                                                                  |
| ---------------------------- | --------------------------------------------------------------------- |
| `database.py`                | asyncpg 連線池管理、`pool_heartbeat_loop`（三服務共用）               |
| `cache.py`                   | cachetools 快取工具                                                   |
| `config_base.py`             | `BaseServiceSettings`：三服務 config 共用基底（DB URL、log level 等） |
| `health_server_base.py`      | `BaseHealthServer`：Discord / Twitch health server 共用基底           |
| `logging_setup.py`           | 結構化 logging 設定（格式、webhook handler 整合）                     |
| `retry_utils.py`             | `parse_retry_after`、`format_duration`（啟動重試工具）                |
| `discord_webhook_handler.py` | 將 ERROR / CRITICAL log 推送至 Discord webhook                        |
| `builtin_commands.py`        | 內建指令定義                                                          |
| `models/`                    | Pydantic 資料模型（channel、command、event、donation 等）             |
| `repositories/`              | 資料庫存取層（per-domain repository 類別）                            |
| `migrations/`                | 自製 migration runner，版本腳本位於 `versions/`                       |

---

## 服務架構

```text
Frontend ──HTTP──▶ API (8000)
                    │
          ┌─────────┼─────────┐
          ▼         ▼         ▼
     PostgreSQL  Twitch Bot  Discord Bot
      (shared)   health:4344  health:8080
```

- **Bot → API**：Bot 透過 HTTP 呼叫 API 取得頻道設定、指令設定、事件設定
- **API → Bot**：API 透過 health endpoint 查詢 Bot 狀態
- **共用 DB**：三個服務共用同一個 PostgreSQL，透過 `shared/` 模組存取
- **錯誤告警**：`shared/discord_webhook_handler` 將後端 ERROR 以上等級 log 推送至 Discord webhook

### `/health` 回應格式（三服務統一）

```json
{ "status": "healthy", "ready": true, "uptime_seconds": 42 }
```

### 本地 Port 對照

| 服務                 | Port   |
| -------------------- | ------ |
| API                  | `8000` |
| Discord Bot health   | `8080` |
| Twitch Bot health    | `4344` |
| PostgreSQL（Docker） | `5433` |

---

## 技術棧

- **Python 3.11+**：語言執行環境
- **FastAPI + uvicorn**：REST API 服務
- **TwitchIO 3**：Twitch Bot 框架（Component 架構、EventSub）
- **discord.py 2**：Discord Bot 框架
- **asyncpg**：PostgreSQL 非同步驅動
- **Pydantic v2 + pydantic-settings**：資料驗證與 config 管理
- **httpx**：HTTP 客戶端（外部 API 呼叫：Riot、Bilibili、TikTok 等）
- **aiohttp**：Bot 健康檢查端點
- **uv**：套件與虛擬環境管理
- **pytest**：測試框架

---

## 前置需求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

> 套件版本約束詳見 [pyproject.toml](pyproject.toml)。

---

## 開發

```bash
cd backend

# 安裝依賴
uv sync

# 各服務獨立啟動（開發用）
uv run python api/main.py
uv run python twitch/main.py
uv run python discord/bot.py
```

> 生產環境使用根目錄的 `docker compose up -d`，不需要手動啟動。

---

## 指令

```bash
uv run pytest              # 執行測試
uv run ruff check .        # Lint
uv run ruff format .       # 格式化
uv run mypy .              # 型別檢查
```

---

## 環境變數

```bash
cp shared.env.example shared.env
cp api/.env.example api/.env
cp twitch/.env.example twitch/.env
cp discord/.env.example discord/.env
```

| 檔案           | 說明                                                         |
| -------------- | ------------------------------------------------------------ |
| `shared.env`   | DB URL、Twitch App 金鑰、OpenRouter、YouTube API Key         |
| `api/.env`     | Twitch OAuth（CLIENT_ID/SECRET）、JWT Secret、服務 URL       |
| `twitch/.env`  | Twitch Bot Token、EventSub 設定                              |
| `discord/.env` | Discord Bot Token、Presence 設定、速率限制閾值               |

> `shared.env` 的 `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` 由 Twitch Bot 與 Discord Bot 共用（社群預覽功能）。API 服務使用 `api/.env` 中的 `CLIENT_ID` / `CLIENT_SECRET`。

---

## DB Migrations

Migration 腳本位於 `shared/migrations/versions/`，使用自製 runner。

```bash
# 手動執行（開發用，Docker 環境下由 migrate 容器自動執行）
uv run python scripts/db_migrate.py
```

---

## API 端點

互動式文件（開發環境）：`http://localhost:8000/docs`（Swagger）或 `/redoc`

| 路由前綴               | 功能                                                 |
| ---------------------- | ---------------------------------------------------- |
| `/api/auth`            | Twitch OAuth 認證、JWT、用戶偏好                     |
| `/api/channels`        | 監控頻道管理、Bot 啟停、冷卻設定                     |
| `/api/commands`        | 自訂指令 CRUD、啟停、公開列表                        |
| `/api/events`          | EventSub 事件設定、Channel Points 兌換               |
| `/api/analytics`       | 場次分析、熱門指令統計                               |
| `/api/game-queue`      | 遊戲排隊狀態、成員管理、設定                         |
| `/api/video-queue`     | 影片佇列播放控制、設定                               |
| `/api/timers`          | 定時訊息 CRUD、啟停                                  |
| `/api/triggers`        | 關鍵字觸發 CRUD、啟停                                |
| `/api/donate`          | 贊助頁資訊、結帳（ECPay / OPay / NewebPay）、webhook |
| `/api/payment-configs` | 金流平台設定                                         |
| `/api/bots`            | Twitch / Discord Bot 狀態與健康檢查                  |
| `/api/stats/channel`   | 頻道統計                                             |
| `/health`, `/status`   | 服務健康檢查（含 DB）                                |

---

## Twitch Bot 指令

### Twitch 一般

- `!hi` — 打招呼（別名 `!hello`、`!hey`）
- `!help` — 指令列表（別名 `!commands`）
- `!uptime` — 直播時長
- `!ai <問題>` — AI 對話
- `!運勢` — 今日運勢（別名 `!fortune`、`!占卜`）
- `!tarot` — 今日塔羅牌（別名 `!塔羅`）
- `!tft` — TFT 排行榜門檻（別名 `!戰棋`）
- `!tft 玩家名#tag` — 查詢指定玩家排名
- `!roll [N]` — 擲 dN 骰（預設 d6，別名 `!骰子`）
- `!choose 選項1 選項2 ...` — 隨機選一個（別名 `!選擇`）

### Twitch 影片佇列

- `!np` — 顯示當前影片、剩餘時間及待播資訊
- `!vq <URL>` — 投遞影片（Mod+）
- `!vq list` — 顯示佇列前 5 首
- `!vq remove` — 移除自己最後一筆未播請求（所有人）
- `!vq skip` — 跳過當前影片（Mod+）
- `!vq clear` — 清空佇列（Mod+）

### Twitch 遊戲排隊

- `!gq` — 查看隊列總覽
- `!gq me` — 查詢自己的排隊狀態（別名 `!gq pos`、`!gq status`，Viewer+）
- `!gq next` — 推進至下一批次（Mod+）
- `!gq kick @user` — 踢出成員（Mod+）
- `!gq clear` — 清空隊列（Mod+）
- `!gq open / close` — 開放 / 關閉報名（Mod+）
- `!gq size <人數>` — 設定每批人數（Mod+）

### Twitch 自訂指令管理（Mod+）

- `!cmd a/add !name [options] text` — 新增指令
- `!cmd e/edit !name [options] [text]` — 編輯指令
- `!cmd d/delete !name` — 刪除指令

### Twitch Owner

- `!comp` — 列出已載入模組
- `!comp l / u / r <module>` — 載入 / 卸載 / 重載模組
- `!comp off` — 關閉 Bot

---

## Twitch EventSub 事件

- **Channel Points** — Niibot 授權、VIP 獎勵、搶第一獎勵
- **Follow** — 追隨通知（24 小時防刷）
- **Subscribe** — 訂閱通知（含禮物訂閱、等級顯示）
- **Raid** — 突襲通知（可設定自動 Shoutout）
- **Stream Online / Offline** — 分析場次追蹤

---

## Discord Bot 指令

### Discord Owner

- `/reload`, `/load`, `/unload`, `/cogs`, `/sync`

### Discord 管理員

- `/clear`, `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`
- `/log set`, `/log unset` — 事件日誌頻道
- `/rate` — Discord API 速率限制統計

### Discord 一般

- `/ping`, `/version`, `/info`, `/userinfo`, `/avatar`, `/help`
- `/game roll`, `/game choose`, `/game rps`, `/game roulette`
- `/fortune`, `/tarot` — 占卜娛樂
- `/tft`, `/tft <名稱#TAG>` — TFT 戰棋段位查詢
- `/giveaway` — 抽獎
- `/ai` — AI 對話
- `/eat` — 隨機推薦餐點
- `/food cat|show` — 餐點分類瀏覽
- `/bday menu` — 生日系統
- 社群連結自動展開 — Instagram、Bilibili、TikTok、Threads、Twitch Clip / 頻道

---

## Discord 伺服器事件日誌

需先以 `/setlog` 設定日誌頻道，以下事件會自動記錄：

- 訊息刪除 / 編輯
- 批量訊息刪除
- 成員身分組異動
