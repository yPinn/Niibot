# Backend

Python 後端，包含 API Server、Twitch Bot、Discord Bot 三個服務，共用 `shared/` 模組。

## 結構

```text
backend/
├── api/        # FastAPI — 認證（Twitch OAuth + JWT）、頻道管理、指令/事件設定
├── twitch/     # Twitch Bot — 聊天指令、Channel Points、EventSub
├── discord/    # Discord Bot — Slash Commands、生日提醒、AI 功能
├── shared/     # 共用 — DB (asyncpg)、Cache、Pydantic Models、Repositories、Migrations
├── scripts/    # 工具腳本 — DB 管理、OAuth token 取得、Discord 資源
├── data/       # 靜態 JSON 資料（運勢、塔羅、遊戲清單等）
├── tests/      # pytest 測試（api / twitch / discord / shared）
├── pyproject.toml
└── uv.lock
```

## 前置需求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

> 以下所有指令均在 `backend/` 目錄下執行。

## 開發

```bash
cd backend

# 安裝依賴
uv sync

# 各服務獨立啟動（開發用）
uv run python api/main.py
uv run python twitch/main.py
uv run python discord/main.py
```

> 生產環境使用根目錄的 `docker compose up -d`，不需要手動啟動。

## 指令

```bash
uv run pytest              # 執行測試
uv run ruff check .        # Lint
uv run ruff format .       # 格式化
uv run mypy .              # 型別檢查
```

## 環境變數

```bash
cp shared.env.example shared.env      # 共用（DATABASE_URL、OPENROUTER_*、YOUTUBE_API_KEY）
cp api/.env.example api/.env
cp twitch/.env.example twitch/.env
cp discord/.env.example discord/.env
```

| 檔案 | 說明 |
| ---- | ---- |
| `shared.env` | 共用 — DB URL、OpenRouter、YouTube API |
| `api/.env` | Twitch OAuth、JWT Secret、服務 URL |
| `twitch/.env` | Twitch Bot 金鑰 |
| `discord/.env` | Discord Bot Token |

## DB Migrations

Migration 腳本位於 `shared/migrations/versions/`，使用自製 runner。

```bash
# 手動執行（開發用，Docker 環境下由 migrate 容器自動執行）
uv run python scripts/db_migrate.py
```

---

## API 端點

### 認證 `/api/auth`
- `GET /twitch/oauth` — Twitch OAuth URL
- `GET /twitch/callback` — OAuth 回調
- `GET /user` — 當前用戶（需認證）
- `POST /logout` — 登出
- `PATCH /api/user/preferences` — 更新用戶偏好

### 頻道 `/api/channels`
- `GET /twitch/monitored` — 監控頻道列表
- `GET /twitch/my-status` — 我的頻道狀態
- `POST /twitch/toggle` — 切換 Bot 狀態
- `GET /defaults` — 頻道預設冷卻設定
- `PUT /defaults` — 更新頻道預設冷卻設定

### 指令設定 `/api/commands`
- `GET /configs` — 取得所有指令設定
- `POST /configs` — 新增自訂指令
- `PUT /configs/{command_name}` — 更新指令設定
- `PATCH /configs/{command_name}/toggle` — 切換指令啟用狀態
- `DELETE /configs/{command_name}` — 刪除自訂指令
- `GET /public/{username}` — 取得頻道公開指令列表

### 事件設定 `/api/events`
- `GET /configs` — 取得事件設定
- `PUT /configs/{event_type}` — 更新事件設定
- `PATCH /configs/{event_type}/toggle` — 切換事件啟用狀態
- `GET /twitch-rewards` — 取得 Twitch 自訂獎勵
- `GET /redemptions` — 取得兌換設定
- `PUT /redemptions/{action_type}` — 更新兌換設定

### 分析 `/api/analytics`
- `GET /summary` — 總覽（`?days=`）
- `GET /sessions/{id}/commands` — 場次指令統計
- `GET /sessions/{id}/events` — 場次事件
- `GET /top-commands` — 熱門指令（`?days=&limit=`）

### Bot 狀態 `/api/bots`
- `GET /twitch/status` — Twitch Bot 狀態
- `GET /twitch/health` — Twitch Bot 健康檢查
- `GET /discord/status` — Discord Bot 狀態
- `GET /discord/health` — Discord Bot 健康檢查

### 其他
- `GET /api/stats/channel` — 頻道統計
- `GET /health` — 健康檢查
- `GET /status` — 詳細狀態（含 DB）

---

## Twitch Bot 指令

**一般**
- `!hi` — 打招呼（別名 `!hello`、`!hey`）
- `!help` — 指令列表（別名 `!commands`）
- `!uptime` — 直播時長
- `!ai <問題>` — AI 對話
- `!運勢` — 今日運勢（別名 `!fortune`、`!占卜`）
- `!rk [player#tag]` — TFT 排名查詢

**自訂指令管理**（Mod+）
- `!cmd a !name [options] text` — 新增指令
- `!cmd e !name [options] [text]` — 編輯指令
- `!cmd d !name` — 刪除指令

**Owner**
- `!comp` — 列出已載入模組
- `!comp l / u / r <module>` — 載入 / 卸載 / 重載模組
- `!comp off` — 關閉 Bot

## Twitch EventSub 事件

- **Channel Points** — Niibot 授權、VIP 獎勵、搶第一獎勵
- **Follow** — 追隨通知（24 小時防刷）
- **Subscribe** — 訂閱通知（含禮物訂閱、等級顯示）
- **Raid** — 突襲通知（可設定自動 Shoutout）
- **Stream Online / Offline** — 分析場次追蹤

---

## Discord Bot 指令

**Owner**
- `/reload`, `/load`, `/unload`, `/cogs`, `/sync`

**管理員**
- `/clear`, `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`
- `/setlog`, `/unsetlog` — 事件日誌頻道
- `/rate_stats`, `/rate_check` — API 速率監控

**一般**
- `/ping`, `/version`, `/info`, `/userinfo`, `/avatar`, `/help`
- `/rps`, `/roll`, `/choose`, `/coinflip`, `/roulette`
- `/fortune`, `/tarot`, `/giveaway`, `/tft`
- `/ai` — AI 對話
- `/eat` — 隨機推薦餐點
- `/food cat|show|add|remove|delete` — 餐點管理
- `/bday menu|init` — 生日系統
