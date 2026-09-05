# Dashboard API

FastAPI 服務（`backend/api/`）提供的路由前綴。開發環境互動式文件：`http://localhost:8000/docs`。

23 個 router 模組掛在 `backend/api/app.py`；前綴以各檔的 `APIRouter(prefix=...)` 為準。

| 前綴                            | Router                       | 功能                                                                               |
| ------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------- |
| `/api/auth`                     | `auth_router`（掛在 `/api`） | Twitch OAuth、JWT cookie、用戶偏好                                                 |
| `/api/tenants`                  | `tenants_router`             | 登入者可存取的工作區、role 與 capability                                           |
| `/api/tenants/.../bot-accounts` | `bot_accounts_router`        | 租戶私有 Bot 名單、Owner invite／reauthorize 與狀態輪詢                            |
| `/api/public/bot-invites`       | `bot_accounts_router`        | 不需登入的安全 consent summary 與 decline                                          |
| `/api/channels`                 | `channels_router`            | 監控頻道管理、Bot 啟停                                                             |
| `/api/commands`                 | `commands_router`            | 指令 CRUD、啟停、公開列表                                                          |
| `/api/events`                   | `events_router`              | EventSub 事件設定、Channel Points 兌換                                             |
| `/api/checkin`                  | `checkin_router`             | 目前租戶的每日簽到時區與回覆模板                                                   |
| `/api/analytics`                | `analytics_router`           | 場次分析、觀眾 Profile、熱門指令統計                                               |
| `/api/analytics/matcher`        | `matcher_router`             | 頻道觀眾重疊分析                                                                   |
| `/api/stats`                    | `stats_router`               | 頻道統計（top chatters／commands）                                                 |
| `/api/game-queue`               | `game_queue_router`          | 遊戲排隊                                                                           |
| `/api/video-queue`              | `video_queue_router`         | 影片佇列                                                                           |
| `/api/timers`                   | `timers_router`              | 定時訊息 CRUD                                                                      |
| `/api/triggers`                 | `message_triggers_router`    | 關鍵字觸發 CRUD                                                                    |
| `/api/crosshairs`               | `crosshairs_router`          | 準星管理、公開庫                                                                   |
| `/api/live-display`             | `community_overlay_router`   | 公開 cursor event feed、租戶 Live Display key 啟用／輪替                           |
| `/api/ai`                       | `ai_settings_router`         | AI 助手設定（角色、enabled、cooldown、min_role、貼圖）                             |
| `/api/donate`                   | `donation_router`            | 贊助結帳（ECPay／OPay／NewebPay／PayPal）、webhook                                 |
| `/api/payment-configs`          | `payment_config_router`      | 金流平台設定                                                                       |
| `/api/bots`                     | `bots_router`                | Bot 狀態查詢                                                                       |
| `/api/discord`                  | `discord_webhook_router`     | Discord 互動 webhook（slash command 簽章驗證）                                     |
| `/api/releases`                 | `releases_router`            | 版本資訊查詢（`git describe`）                                                     |
| `/api/admin`                    | `admin_router`               | 管理員工具（限 Owner）；聚合 `routers/admin/` 下 `logs`／`db`／`modules` 子 router |
| `/health`、`/status`            | —                            | 服務健康檢查                                                                       |

## 安全機制

| 項目         | 做法                                                                  |
| ------------ | --------------------------------------------------------------------- |
| Session      | JWT httponly cookie（HS256，預設 7 天，`JWT_EXPIRE_DAYS` 可調）       |
| OAuth CSRF   | HMAC-SHA256 簽章的 state 參數                                         |
| Bot invite   | public token + state nonce 雙雜湊、30 分鐘、一次性、callback row lock |
| Twitch token | `TWITCH_TOKEN_ENCRYPTION_KEY` 的 versioned Fernet envelope            |
| 全域標頭     | CSP、HSTS 等安全標頭中介層                                            |
| 金流 webhook | 驗簽——CheckMacValue SHA-256、NewebPay AES-256-CBC + TradeSha          |
| Overlay feed | UUID capability key、每頁上限 100、IP + key rate limit、`no-store`    |

## Tenant collaboration API rollout

完整 schema、RBAC、OAuth 與 rollout 規格見
[Bot Accounts、租戶協作與 Twitch MOD 同步](../architecture/bot-accounts-and-collaboration.md)。

目前可呼叫：

- `GET /api/tenants`：server-side 解析工作區與 capability。
- `GET /api/tenants/{channel_id}/bot-accounts`：Owner/MOD 安全摘要；system Niibot + 該 tenant mappings。
- `POST /api/tenants/{channel_id}/bot-accounts/invites`：Owner-only；需
  `X-Niibot-Action: bot-account-management`。
- `POST /api/tenants/{channel_id}/bot-accounts/{bot_id}/reauthorize-invite`：Owner-only、expected-account reset。
- `GET /api/tenants/{channel_id}/bot-accounts/invites/{invite_id}`：Owner-only status polling，不回 capability secret。
- `GET/POST /api/public/bot-invites/{public_token}`：safe consent summary／decline；nonce 放 query。
- `GET /api/auth/twitch/bot/callback`：不建立 User、session、membership 或 tenant。
- `GET /api/auth/twitch/collaborator/oauth|callback`：identity-only collaborator session。
- `POST /api/admin/bot-accounts/system-default/reset-invite`：system owner-only Niibot token reset。

仍在 Phase 3–5：Bot unlink／sender selection、`/members` manual MOD grants、
`/collaboration-settings` 與 Twitch MOD sync。既有 private feature routers 尚未全數遷移到 `{channel_id}` path。

## Community Overlay feed

- `GET /api/live-display/public/events`：以 `X-Overlay-Key: <uuid>` 驗證；初次只回目前 `cursor`，不重播歷史。
- `GET /api/live-display/public/events?after_id=<cursor>`：同樣以 header 驗證，依 id 回傳未過期事件。
- `GET/PATCH /api/live-display/settings`：已啟用租戶讀取 key／啟停 feed。
- `POST /api/live-display/settings/rotate-key`：輪替 capability key，舊 OBS URL 立即失效。
- `GET /api/live-display/settings/blocks/<block_type>/theme`：取得目前租戶草稿與已發布 revision。
- `PATCH /api/live-display/settings/blocks/<block_type>/theme/draft`：完整覆寫目前租戶草稿，不影響 OBS；body 需帶
  `expected_draft_version`。
- `POST /api/live-display/settings/blocks/<block_type>/theme/publish`：body 需帶 `expected_draft_version`；發布草稿為不可變
  revision，內容未變時不重複建版。
- `POST /api/live-display/settings/blocks/<block_type>/theme/reset-draft`：body 需帶 `expected_draft_version`，以已發布 revision
  重設目前租戶草稿。
- `GET /api/live-display/public/theme`：以 `X-Overlay-Key: <uuid>` 只回啟用中的已發布樣式。

OBS URL 將 public key 放在 fragment，瀏覽器不會把 fragment 傳到 server；公開 API 再以
`X-Overlay-Key` header 驗證，避免 key 出現在 request path、query、history referrer 與一般 access log。
Feed 與 theme 都不回傳 `channel_id` 或穩定的 actor user id、不接受 client 指定 tenant，且回應使用
`Cache-Control: no-store`。公開端點同時套 IP-only 與 IP+capability 限流，隨機輪替 UUID 不能重開額度。
私有 mutation 需使用 JSON request body（輪替 key 除外）並帶
`X-Niibot-Action: live-display`；自訂 header 會觸發 CORS preflight，阻止一般 HTML form 跨站送出。

Theme schema v1 固定為 `checkin-card` allowlist：`surface_color`、`accent_color`、`text_color`、
`placement`、`radius_px`、`display_ms`、`motion`。未知／缺漏欄位與型別轉換一律拒絕；目前不接受圖片、
外部資源、HTML、CSS 或 JavaScript。色彩對比不在後端硬性驗證範圍——這是頻道自己 OBS 畫面的裝飾配色，
不是所有人都必須使用的介面，因此 Dashboard 僅在草稿編輯器顯示對比建議，不阻擋儲存或發布。
草稿僅由同租戶私有端點讀寫，公開 renderer 永遠只讀已發布版本。
新 profile 的共用預設位置為 `bottom-left`、顯示時間為 4000ms；Tarot 使用相同 schema，但 block 預設另設為
16px 圓角與 5000ms 顯示時間。時間從事件開始播放時計算；四角位置與其他 allowlisted 欄位仍可由頻道草稿調整後發布。

前端 OBS source 使用 `/live-display#key=<uuid>`，初次 handshake 不重播；只有 fragment 明確加入
`preview=1` 才會以 `after_id=0` 讀取仍未過期事件。renderer 每 5 秒檢查 published revision，並在
capability／preview 改變時清除 cursor、去重集合、播放佇列與 theme，舊請求不得跨租戶落地。
開發環境可由 broadcaster 在聊天室輸入
`!ovltest [1-9999]` 產生短效 preview event；此指令不修改正式簽到 ledger。

登入後可從 `Live Display`（`/modules/live-display`）管理上述設定與網址；Vite development
另有不呼叫租戶 settings API 的 `/dev/live-display` 視覺預覽，production build 會移除該路由。

## Events 與 Twitch 頻道點數

- `GET /api/events/twitch-rewards`：以目前登入租戶的 broadcaster token 讀取自訂獎勵，回傳穩定 `id`、
  `title`、`cost`、啟用／暫停／庫存、是否略過請求佇列、每場總上限與每人每場上限。
- `GET /api/events/redemptions`：回傳頻道的 action 設定；`checkin` 代表 Twitch 點數簽到，並包含 nullable
  `reward_id`、相容用 `reward_name` 與 `enabled`。
- `PUT /api/events/redemptions/{action_type}`：綁定 `reward_id`／`reward_name` 並啟停監聽；endpoint 的 tenant
  由登入狀態決定，不接受 body 指定 `channel_id`。

Channel Points 簽到只需 `channel:read:redemptions`。Niibot 不要求 `channel:manage:redemptions`，因此上述 API
不會建立、修改、完成、取消或退款 Twitch 獎勵；成本與單場限制須回 Twitch Dashboard 調整。同日重複兌換
會被 Daily Check-in 唯一鍵阻止增加 count，但 Niibot 無法退回已消耗點數。

## Daily Check-in settings

- `GET /api/checkin/settings`：讀取目前登入租戶的 IANA timezone、簽到成功模板、同日重複模板，
  以及 `reply_delay_seconds`（聊天回覆延遲秒數，補償 Twitch 廣播延遲，範圍 0–30，預設 0）。
- `PATCH /api/checkin/settings`：部分更新上述欄位；body 嚴格禁止 `channel_id` 與未知欄位，mutation 必須帶
  `X-Niibot-Action: checkin-settings`。

模板只接受 `$(@user)`、`$(user)`、`$(count)`、`$(date)`；server 會同時驗證未知變數與 Twitch
500 字元的最壞輸出長度。聊天指令與 Channel Points `checkin` adapter 共用同一份 tenant 設定。
前端 `/events` 只管理 EventSub 回覆；`/channel-points` 管理 reward → action 映射，並由每日簽到列開啟
獨立的 `Check-in settings` 編輯面。`Community Overlay` 只顯示目前 reward 綁定摘要並導向
`/channel-points`，不提供第二個 mutation 入口。

## 租戶邊界

`channels_router` 與 `commands_router` 的 channel-scoped 端點已改用
`require_tenant_access` / `require_self_tenant_access` 依賴，其餘 router 仍走 legacy 的
`get_current_channel_id` shim。遷移進度與設計見
[architecture/admission-and-tenancy.md](../architecture/admission-and-tenancy.md)。
