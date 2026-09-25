# 架構總覽

Niibot 是多平台直播整合系統，由三個 Python 服務 + 一個前端組成，共用單一 PostgreSQL。
另有一個選用的 Threads 抓取 sidecar（scrapling）。本文串起全貌；子系統細節見各自文件。

- 多租戶 / 入會狀態機：[admission-and-tenancy.md](admission-and-tenancy.md)
- Bot 帳號 / 授權生命週期 / Owner／MOD 協作（Phase 0–3 已交付）：[bot-accounts-and-collaboration.md](bot-accounts-and-collaboration.md)
- 出席 / 簽到 / 社群 Overlay：[attendance-and-community-overlays.md](attendance-and-community-overlays.md)
- 後端結構：[backend/README.md](../../backend/README.md) · API 端點：[api-endpoints.md](../reference/api-endpoints.md)
- 版本規範：[versioning.md](../reference/versioning.md)

---

## 服務拓樸

```text
                       Cloudflare Pages
                    ┌────────────────────┐
   使用者 ─HTTPS──▶ │ Frontend (React 19) │
                    │  functions/ 反向代理 │
                    └─────────┬───────────┘
                              │ /api/*
                  Cloudflare Tunnel
                              │
                    ┌─────────▼───────────┐
                    │   API (FastAPI)     │  :8000  /docs (OpenAPI)
                    └─────────┬───────────┘
                              │ asyncpg pool
          ┌───────────────────┼───────────────────┐
          │                   │                   │
   ┌──────▼──────┐     ┌──────▼──────┐     ┌──────▼──────┐
   │ PostgreSQL  │◀───▶│ Twitch Bot  │     │ Discord Bot │
   │  (shared)   │     │ health:4344 │     │ health:8080 │
   └─────────────┘     │  EventSub   │     │   Cogs      │
                       └─────────────┘     └─────────────┘
```

三個服務共用 `backend/shared/`（DB pool、cache、repositories、models、migrations），
但**各自獨立程序、獨立部署**。唯一的耦合是 PostgreSQL（資料 + 跨程序訊號）。

| 服務        | 技術         | 網路介面                         | 健康檢查       |
| ----------- | ------------ | -------------------------------- | -------------- |
| API         | FastAPI      | container `:8000`；host 埠依環境 | `/health`      |
| Twitch Bot  | TwitchIO 3   | EventSub WebSocket               | `:4344/health` |
| Discord Bot | discord.py 2 | Gateway                          | `:8080/health` |
| PostgreSQL  | PG 16        | container `:5432`；僅 dev 發布   | —              |

**scrapling**（`backend/scrapling/`）是選用的旁掛服務：discord 的 social preview 用它抓
JS 算圖的 Threads 內容。不共用 `backend/shared/`、不在 `compose.yaml`、不進 CI 部署——
需要時獨立啟動並設 `SCRAPLING_HOST`；未設定時 Threads 走純 OG 降級路徑。
見 [integrations/scrapling.md](../integrations/scrapling.md)。

---

## 多租戶邊界

每個 Twitch 廣播主的頻道是一個獨立 **tenant**。三項職責刻意拆在不同 service，
勿在 router / repository 內耦合：

- **IdentityService** — `(platform, platform_user_id)` find_or_link
- **AdmissionService** — `memberships.status` 狀態機 + `membership_events` 稽核軌跡
- **TenantService** — 頻道擁有權 + per-channel RBAC（`channel_members`）

channel-scoped 資料表一律以 `channel_id` 過濾；migration 083 已定義 Postgres RLS policies，
但目前尚未 enable，也尚未在所有 repository transaction 綁定 tenant GUC，因此現行第二道防線仍在 rollout 中。
完整設計見 [admission-and-tenancy.md](admission-and-tenancy.md)。

---

## 即時設定傳播（LISTEN / NOTIFY）

設定改動需即時反映到正在運行的 Bot，又不能讓 Bot 輪詢 DB。Niibot 用 PostgreSQL 的
`LISTEN/NOTIFY` 做跨程序訊號：

```text
Dashboard 改設定 ──▶ API 寫入 DB ──▶ pg_notify(channel, payload)
                                          │
                          Twitch Bot pg_listen() ◀─┘
                                          │
                          重載對應記憶體狀態（免重啟）
```

| NOTIFY 頻道               | 觸發來源                                 | Bot 反應                                        |
| ------------------------- | ---------------------------------------- | ----------------------------------------------- |
| `config_change`           | 指令 / 觸發 / 計時器 / 一般 AI 設定 CRUD | 重載該頻道設定；明確停用記憶時另清除 AI session |
| `assistant_scope_changed` | 啟用 Role-play revision／切回 Persona    | 失效 AI cache 並淘汰該頻道其他角色 scope        |
| `channel_toggle`          | 頻道啟停 Bot                             | 訂閱 / 取消 EventSub、檢查 mod 權限             |
| `new_token`               | OAuth 新 token                           | 載入新 broadcaster token                        |
| `token_reauth`            | token 失效                               | 標記頻道需重新授權                              |
| `bot_token_updated`       | Web Bot OAuth callback                   | 清除 system Bot token cache 並熱載入            |

實作：Twitch Bot 用 `pg_listen()`（`twitch/core/pg_listener.py`）開**專用連線**做
LISTEN（不佔用 pool），斷線自動重連。

`channel_toggle` 不只由 dashboard 觸發：migration 084 起，`memberships.status` 進出
`active` 會經 DB trigger 連動 `channels.enabled`，因此核准／停權會即時讓 Bot 加入或離開頻道，
無需應用層呼叫。詳見 [admission-and-tenancy.md](admission-and-tenancy.md)。

行內快取 `AsyncTTLCache`（`shared/cache.py`，LRU + TTL）負責程序內讀取加速；
`pg_notify` 負責**跨程序**失效。兩者互補。

---

## [AI Assistant Harness](ai-assistant-harness.md)

`shared/assistant/` 將 prompt 編譯、provider adapter、有界 fallback、circuit breaker 與輸出整理分開。
呼叫端只提交 provider-neutral 的 typed sections；registry 要求 key 與 model 都明確設定，不再使用退役模型的
隱性預設值。health/status 直接呈現實際 registry 與 circuit 狀態，但不包含 key、prompt 或聊天內容。

```text
core policy → product contract → channel persona → retrieved context → history → user input
       │
       ▼
PromptCompiler → BoundedRouter → OutputProcessor → Twitch / Discord renderer
```

固定免費路由依 qualification 的成功率、限流與延遲排序：

- Twitch — Groq `openai/gpt-oss-120b` → OpenRouter `inclusionai/ling-3.0-flash-vl:free`；
  8 秒總 deadline、每次最多 4 秒、最多 2 次 attempt。
- Discord — Groq `openai/gpt-oss-120b` → Gemini `gemini-3.5-flash` → OpenRouter
  `inclusionai/ling-3.0-flash-vl:free`；40 秒總 deadline、每次最多 15 秒、最多 3 次 attempt。

只有 timeout、429、網路／5xx 與 model unavailable 會 fallback；驗證錯誤與安全拒答不會藉下一模型繞過，
401/403 會把 provider circuit 標成 unhealthy。OpenRouter adapter 強制零價格限制，不允許靜默切到付費模型。
`backend/data/free_models.json` 只保留為手動研究清單，不參與 production 動態路由。AI 知識包注入見
[static-data.md](../reference/static-data.md)。

---

## 部署拓樸

後端透過 **Cloudflare Tunnel** 對外，無需開放主機埠；前端在 **Cloudflare Pages**，
`/api/*` 由 Pages Functions 代理回後端。

各環境用 `compose.yaml`（base）+ `compose.<dev|stg|prod>.yaml`，彼此以 project / network / volume 隔離。
`migrate` 容器在部署時自動跑 DB migration；版本由 `git describe` 決定，前後端共用同一 tag。
完整指令、埠對照、CI/CD 密鑰見 [deployment.md](../guides/deployment.md)。

---

## 資料流範例

### Twitch OAuth 登入

```text
前端 ─▶ /api/auth/login ─▶ Twitch OAuth ─▶ /api/auth/callback
  └─ IdentityService.find_or_link ─▶ 簽發 JWT httponly cookie（HS256）
```

### Bot OAuth 邀請

```text
Owner Settings ─▶ 建立 30 分鐘 invite URL ─▶ 朋友以 Bot Twitch 帳號授權
  └─ HMAC state + DB nonce／expiry／row lock
      └─ encrypted bot token + tenant mapping + audit（單一 transaction）
          └─ system Niibot reset 時 pg_notify('bot_token_updated') 熱載入
```

Bot callback 永不建立 Dashboard session／membership／tenant；自訂 Bot 只透過
`channel_bot_accounts` 對邀請 tenant 可見。Per-tenant sender 仍待 Phase 3。

### 聊天指令觸發

```text
觀眾在 Twitch 聊天打指令 ─▶ Twitch Bot（記憶體中的頻道設定）
  └─ 命中 ─▶ 回覆；設定來源為 DB，經 config_change NOTIFY 保持最新
```

### Dashboard 改設定

```text
前端 ─▶ /api/commands（CRUD）─▶ DB 寫入 + pg_notify('config_change')
  └─ Twitch Bot 即時重載，無需重啟
```

---

## 延伸閱讀

- 多租戶 / Admission：[admission-and-tenancy.md](admission-and-tenancy.md)
- 出席 / 簽到 / 社群 Overlay：[attendance-and-community-overlays.md](attendance-and-community-overlays.md)
- 後端結構：[backend/README.md](../../backend/README.md)
- API 端點：[api-endpoints.md](../reference/api-endpoints.md)
- 靜態資料 / AI 知識包：[static-data.md](../reference/static-data.md)
- 版本規範：[versioning.md](../reference/versioning.md)
- 媒體抓取：[fixtweet](../integrations/fixtweet.md) ·
  [instafix](../integrations/instafix.md) · [scrapling](../integrations/scrapling.md)
