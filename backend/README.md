# Backend

三個 Python 服務（api、twitch、discord）共用 `shared/` 模組，各自獨立程序與部署。
另有選用的 `scrapling/` sidecar。開發與部署見 [docs/guides/](../docs/guides/)。

## 結構

```text
backend/
├── api/        # FastAPI — Twitch OAuth + JWT、Dashboard API
│   ├── core/       # config、dependencies、rate_limit、logging
│   ├── routers/    # 路由層（薄，僅 I/O 與授權）；admin/ 為聚合子套件
│   └── services/   # 業務邏輯（含 Identity / Admission / Tenant，見下方）
├── twitch/     # Twitch Bot — 聊天指令、VideoQueue、GameQueue、Channel Points、EventSub
├── discord/    # Discord Bot — Slash Commands、生日提醒、社群預覽、AI
├── scrapling/  # 選用：Threads 抓取 sidecar（獨立部署，見 docs/integrations/scrapling.md）
├── shared/     # 共用模組（見下方）
├── scripts/    # DB 管理、OAuth token 工具
├── data/       # 靜態資料（見 docs/reference/static-data.md）
├── tests/      # pytest
├── pyproject.toml
└── uv.lock
```

### 多租戶服務層（`api/services/`）

Niibot 為多租戶——每個 Twitch 頻道是獨立 tenant。三項職責刻意拆分，勿在 router／repository 內耦合：

- **`IdentityService`** — 依 `(platform, platform_user_id)` find_or_link；identity row 遺失時自我修復。
- **`AdmissionService`** — `memberships.status` 狀態機（pending／active／suspended／rejected），
  每次轉換附寫 `membership_events`。
- **`TenantService`** — 頻道擁有權 + per-channel RBAC（`channel_members`）。

`memberships` 為真實來源；`users.is_activated` 與 `activation_requests` 為 legacy，僅供回滾。
目前 `channels_router` 與 `commands_router` 已改用 `require_tenant_access` 依賴，其餘 router 仍走
legacy 的 `get_current_channel_id`。完整設計與遷移進度見
[docs/architecture/admission-and-tenancy.md](../docs/architecture/admission-and-tenancy.md)。

### `shared/` 模組

| 模組                         | 說明                                                         |
| ---------------------------- | ------------------------------------------------------------ |
| `database.py`                | asyncpg 連線池管理、`pool_heartbeat_loop`                    |
| `cache.py`                   | `AsyncTTLCache`（LRU + TTL）；搭配 `pg_notify` 即時失效      |
| `config_base.py`             | `BaseServiceSettings`：三服務共用 config 基底                |
| `health_server_base.py`      | `BaseHealthServer`：Discord／Twitch health server 基底       |
| `logging_setup.py`           | 結構化 logging（含 Discord webhook error handler）           |
| `builtin_commands.py`        | 內建指令定義與別名映射                                       |
| `builtin_timers.py`          | 內建定時訊息定義                                             |
| `ai_provider.py`             | 多 AI Provider 鏈（Groq／Gemini／OpenRouter），自動 fallback |
| `crypto.py`                  | OAuth token／金流金鑰加解密（AES）                           |
| `discord_webhook_handler.py` | 將 ERROR 以上 log 推送至 Discord webhook                     |
| `packs.py`                   | AI 知識包（`data/packs/`）載入、key 比對與 token 預算        |
| `retry_utils.py`             | 通用 async 重試／backoff helper                              |
| `twitch_scopes.py`           | Twitch OAuth scope 常數與分組                                |
| `models/`                    | Pydantic 資料模型                                            |
| `repositories/`              | 資料庫存取層（per-domain）                                   |
| `migrations/`                | 自製 migration runner；版本腳本在 `versions/`                |

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
| Twitch Bot health    | `4344` |
| Discord Bot health   | `8080` |
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

環境變數對照見 [docs/guides/environment.md](../docs/guides/environment.md)。
本機開發可建 `shared.env.local`（gitignored）覆蓋 `shared.env`。

DB migration 手動執行：`uv run python scripts/db_migrate.py`
（Docker 環境下由 `migrate` 容器自動執行）。

## API 端點

開發環境互動式文件：`http://localhost:8000/docs`。
路由前綴與安全機制見 [docs/reference/api-endpoints.md](../docs/reference/api-endpoints.md)。
