# Dashboard API

FastAPI 服務（`backend/api/`）提供的路由前綴。開發環境互動式文件：`http://localhost:8000/docs`。

27 個 router 模組掛在 `backend/api/app.py`；前綴以各檔的 `APIRouter(prefix=...)` 為準。
「前端頁面」欄位是這個 API 實際餵給哪個 dashboard 路由／nav 項目——用來在「從 UI 找後端」或
「從後端找 UI」時直接對照，不必每次重新搜尋。沒有獨立頁面（被其他頁面內嵌，或純資料來源）的
router 標記為「（無獨立頁面）」。

| 前綴                             | Router                       | 功能                                                                               | 前端頁面                                                           |
| -------------------------------- | ---------------------------- | ---------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `/api/auth`                      | `auth_router`（掛在 `/api`） | Twitch OAuth、JWT cookie、用戶偏好                                                 | `/login`、`/activate`                                              |
| `/api/tenants`                   | `tenants_router`             | 登入者可存取的工作區、role 與 capability                                           | （無獨立頁面，跨頁共用）                                           |
| `/api/tenants/.../bot-accounts`  | `bot_accounts_router`        | Bot／實況主授權狀態、Owner invite、重查、移除與解除                                | Settings、`/bot-invite/:publicToken`、`/bot-auth/result`           |
| `/api/tenants/.../roleplay-sets` | `roleplay_router`            | 租戶私有角色設定集的草稿、發布、啟用與封存                                         | （尚無頁面）                                                       |
| `/api/public/bot-invites`        | `bot_accounts_router`        | 不需登入的安全 consent summary 與 decline                                          | 同上                                                               |
| `/api/channels`                  | `channels_router`            | 監控頻道管理、Bot 啟停                                                             | Overview（`/`）                                                    |
| `/api/commands`                  | `commands_router`            | 指令 CRUD、啟停、公開列表                                                          | `/commands`                                                        |
| `/api/events`                    | `events_router`              | EventSub 事件設定、Channel Points 兌換                                             | `/events`；兌換設定併入 `/channel-points`                          |
| `/api/vip`                       | `vip_router`                 | VIP 門檻、獎勵規則與序號發放                                                       | 併入 `/channel-points`（VipSettingsSheet）                         |
| `/api/checkin`                   | `checkin_router`             | 目前租戶的每日簽到時區與回覆模板                                                   | 併入 `/channel-points`（CheckinSettingsSheet／CheckinLeaderboard） |
| `/api/analytics`                 | `analytics_router`           | 場次分析、觀眾 Profile、熱門指令統計                                               | `/analytics/insights`                                              |
| `/api/analytics/matcher`         | `matcher_router`             | 頻道觀眾重疊分析                                                                   | `/analytics/matcher`                                               |
| `/api/stats`                     | `stats_router`               | 頻道統計（top chatters／commands）                                                 | Overview 小工具                                                    |
| `/api/game-queue`                | `game_queue_router`          | 遊戲排隊                                                                           | `/modules/game-queue`、`/:username/game-queue/overlay`             |
| `/api/video-queue`               | `video_queue_router`         | 影片佇列                                                                           | `/modules/video-queue`、`/:username/video-queue/overlay`           |
| `/api/timers`                    | `timers_router`              | 定時訊息 CRUD                                                                      | `/timers`                                                          |
| `/api/triggers`                  | `message_triggers_router`    | 關鍵字觸發 CRUD                                                                    | （目前 build 未掛 nav 項目）                                       |
| `/api/crosshairs`                | `crosshairs_router`          | 準星管理、公開庫                                                                   | `/modules/crosshairs`、`/:username/crosshairs`                     |
| `/api/live-display`              | `community_overlay_router`   | 公開 cursor event feed、租戶 Live Display key 啟用／輪替                           | `/modules/live-display`、公開 `/live-display`                      |
| `/api/ai`                        | `ai_settings_router`         | AI 助手設定（角色、enabled、cooldown、min_role、貼圖）                             | `/modules/ai`                                                      |
| `/api/donate`                    | `donation_router`            | 贊助結帳（ECPay／OPay／NewebPay／PayPal）、webhook                                 | `/donate/:username`                                                |
| `/api/payment-configs`           | `payment_config_router`      | 金流平台設定                                                                       | （無獨立頁面，設定子面板）                                         |
| `/api/bots`                      | `bots_router`                | Bot 狀態查詢                                                                       | （無獨立頁面，狀態小工具）                                         |
| `/api/discord`                   | `discord_webhook_router`     | Discord 互動 webhook（slash command 簽章驗證）                                     | `/discord`                                                         |
| `/api/client-errors`             | `client_errors_router`       | 前端 client-side 錯誤回報與查詢                                                    | 併入 `/admin/monitor`                                              |
| `/api/releases`                  | `releases_router`            | 版本資訊查詢（`git describe`）                                                     | `/docs/releases`                                                   |
| `/api/admin`                     | `admin_router`               | 管理員工具（限 Owner）；聚合 `routers/admin/` 下 `logs`／`db`／`modules` 子 router | `/admin`、`/admin/monitor`、`/admin/modules`                       |
| `/health`、`/status`             | —                            | 服務健康檢查                                                                       | —                                                                  |

## 已知的命名分歧

大多數 router 的前綴／類別／table／前端頁面都同源（例如 `crosshairs_router` ↔
`CrosshairRepository` ↔ `crosshairs` table ↔ 「Crosshair Repo」頁面），只是英翻中或單複數差異，
不是分歧。以下 3 組是盤點後找到、值得記住但**刻意不去改**的分歧——改的成本／風險都大於「有人偶爾
要多想一步」這個問題本身：

- **`/channel-points` 頁面是 `events`／`vip`／`checkin` 三個獨立 router 拼出來的，後端沒有
  `channel_points` 這個 module、service 或 table。** 這是刻意的關注點分離（兌換設定、VIP 制度、
  每日簽到本來就是三個不同權責），不是命名錯誤，所以不「修」；但因為後端完全沒有對應名稱可查，
  容易讓人從 UI 頁面回頭找程式碼時撲空，故記錄於此。
- **`bot_accounts_router` 是唯一沒有自己專屬 prefix 的 router**，端點分散在
  `/api/tenants/.../bot-accounts`、`/api/public/bot-invites`（未來可能還有
  `/api/admin/bot-accounts/...`）。不改的原因：`/api/public/bot-invites/...` 這類路徑可能已經被
  寄出去的邀請連結引用，貿然改 prefix 等於讓已發出的連結失效，風險不成比例。
- **`game_queue_router` 對應的 table 叫 `game_queue_entries`，但 `video_queue_router` 對應的
  table 直接叫 `video_queue`**——同類型的兩個佇列功能，table 命名慣例不一致。這純粹是內部 DB
  命名，不影響 API 或 UI；改名需要一支 migration（`ALTER TABLE ... RENAME`）加上更新 repository
  裡的所有查詢，屬於資料庫 schema 變更而非小改動，因此這次不順手調整，僅記錄在此供未來需要時參考。

以上皆與「`ai_settings` table 對應『AI Assistant』頁面」這種情況不同——`ai_settings`／
`checkin_settings`／`video_queue_settings` 都是「`<功能>_settings` 儲存該功能設定」的一致慣例，
頁面顯示用功能本身的名字（AI Assistant、Daily Check-in、Video Queue）很正常，不是命名分歧。

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
- `POST /api/tenants/{channel_id}/bot-accounts/{bot_id}/authorization-check`：Owner-only；立即驗證 token、身分與 scopes。
- `DELETE /api/tenants/{channel_id}/bot-accounts/{bot_id}`：Owner-only；active／desired 回 409，只移除該 tenant mapping。
- `POST /api/tenants/{channel_id}/bot-accounts/invites`：Owner-only；需
  `X-Niibot-Action: bot-account-management`。
- `POST /api/tenants/{channel_id}/bot-accounts/{bot_id}/reauthorize-invite`：Owner-only、expected-account reset。
- `GET /api/tenants/{channel_id}/bot-accounts/invites/{invite_id}`：Owner-only status polling，不回 capability secret。
- `GET/POST /api/public/bot-invites/{public_token}`：safe consent summary／decline；nonce 放 query。
- `GET /api/auth/twitch/bot/callback`：不建立 User、session、membership 或 tenant。
- `GET /api/auth/twitch/collaborator/oauth|callback`：identity-only collaborator session。
- `POST /api/admin/bot-accounts/system-default/reset-invite`：system owner-only Niibot token reset。
- `GET /api/tenants/{channel_id}/broadcaster-authorization`：Owner/MOD 安全摘要。
- `POST /api/tenants/{channel_id}/broadcaster-authorization/check`：Owner-only 手動驗證。
- `DELETE /api/tenants/{channel_id}/broadcaster-authorization`：Owner-only；停用頻道、撤銷 Owner sessions 並解除 token，
  但保留設定與歷史紀錄。

授權檢查與解除 mutation 使用 `X-Niibot-Action: twitch-authorization-management`。仍在 Phase 4–5：`/members` manual MOD grants、
`/collaboration-settings` 與 Twitch MOD sync。既有 private feature routers 尚未全數遷移到 `{channel_id}` path。

## Canon Role-play authoring API

角色設定集以頻道 workspace 為 owner；所有路徑都由 `require_tenant_access` 解析登入者可操作的
`channel_id`，不沿用只代表登入者自己頻道的 `require_activated`，request body 也不能另行指定 tenant。
目前可呼叫：

- `GET /api/tenants/{channel_id}/roleplay-sets`：列出未封存設定集；`include_archived=true` 可包含封存項目，
  list response 不傳回完整草稿。
- `POST /api/tenants/{channel_id}/roleplay-sets`：建立含 strict role-play document 的私人草稿。
- `GET /api/tenants/{channel_id}/roleplay-sets/{set_id}`：讀取完整草稿與目前發布摘要。
- `PATCH /api/tenants/{channel_id}/roleplay-sets/{set_id}`：以 `expected_draft_version` 更新草稿與名稱；版本落後回
  `409 ROLEPLAY.VERSION_CONFLICT`。
- `POST /api/tenants/{channel_id}/roleplay-sets/{set_id}/revisions`：驗證、編譯並發布 immutable revision；不會自動啟用。
- `PUT /api/tenants/{channel_id}/roleplay-sets/{set_id}/active-revision`：啟用同 tenant、同設定集的已發布 revision。
- `DELETE /api/tenants/{channel_id}/active-roleplay`：切回既有 Persona Assistant。
- `DELETE /api/tenants/{channel_id}/roleplay-sets/{set_id}`：soft archive；正在使用的設定集必須先切換。

所有 mutation 都要求 `X-Niibot-Action: roleplay-settings`，並套用 user + tenant + IP 限流；body schema
拒絕未知欄位與型別轉換。只有啟用 revision 或切回 Persona 會發送 versioned
`assistant_scope_changed` 通知，讓其他 API instance 精準失效該頻道的 `ai_settings` cache；編輯草稿、發布未啟用
revision 與封存非 active 設定集都不通知 runtime。Twitch compact runtime 與 revision-scoped memory 已接入；
非技術 Dashboard wizard 尚未接入，因此目前仍需直接呼叫 API 才能建立與啟用故事角色。

## Community Overlay feed

- `GET /api/live-display/public/stream`：以 `X-Overlay-Key: <uuid>` 驗證的長連線 SSE
  (`text/event-stream`)。由 PostgreSQL `NOTIFY` 喚醒後重讀 durable table 送出 `event: snapshot`／
  `event: update`（依 `after_id` cursor 補未過期事件）與 `event: heartbeat`；renderer 目前使用的傳輸，
  取代下方 `events` polling 端點。5 分鐘 hard lease 到期由 client 帶 cursor 自動重連；詳見
  [docs/guides/cloudflare-pages.md](../guides/cloudflare-pages.md) 的 Live Display stream contract。
- `GET /api/live-display/public/events`（legacy）：以 `X-Overlay-Key: <uuid>` 驗證；初次只回目前 `cursor`，不重播歷史。
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

Daily Check-in 成功時仍送出 `event_type = checkin.recorded`、`schema_version = 1`。新事件的 payload
可額外包含 validated `collection` snapshot：draw／pool／algorithm、card revision、set、rarity、同源 artwork
derivatives、`is_new`、`copy_count` 與進度。欄位是 additive optional contract，沒有該欄位的舊事件仍合法；
前端遇到缺漏或 malformed collection 會顯示 legacy 簽到卡。現階段沒有租戶自訂 cards／pool 管理 API，也沒有
viewer collection 查詢端點。

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
新 profile 的共用預設位置為 `bottom-left`、顯示時間為 5000ms；既有已發布的 4000ms revision 不會被改寫。
Tarot 使用相同 schema，block 預設另設為 16px 圓角與 5000ms 顯示時間。時間從事件開始播放時計算；
四角位置與其他 allowlisted 欄位仍可由頻道草稿調整後發布。Collection binder 在單筆 budget 內依序完成
開書、印卡、入槽／重複合併與關書；FIFO 提升下一筆前會重新檢查 expiry，且每筆事件保留入列時的 theme。

前端 OBS source 使用 `/live-display#key=<uuid>`，初次 handshake 不重播；只有 fragment 明確加入
`preview=1` 才會以 `after_id=0` 開啟 `stream` 連線讀取仍未過期事件。renderer 由 SSE push 更新
published revision（不再輪詢），並在 capability／preview 改變時中止舊連線、清除 cursor、去重集合、
播放佇列與 theme，舊連線的晚到 frame 不得跨租戶落地。
開發環境可由 broadcaster 在聊天室輸入
`!ovltest [1-9999]` 產生短效 preview event；此指令不修改正式簽到 ledger。

登入後可從 `Live Display`（`/modules/live-display`）管理上述設定與網址；Vite development
另有不呼叫租戶 settings API 的 `/dev/live-display` 視覺預覽，production build 會移除該路由。

## Video Queue overlay stream

- `GET /api/video-queue/public/{username}/stream`：無需認證的長連線 SSE（OBS overlay 用，比照公開
  REST 端點的匿名模式）。由 PostgreSQL `NOTIFY` 喚醒後重讀目前佇列狀態，僅在重建結果與上次送出的
  payload 不同時才送 `event: update`；無 cursor／事件回放語意——狀態是單一目前快照，重連只會拿到
  最新一份，不像 Live Display 的事件日誌需要補送歷史。payload 不含 `enabled`（overlay 從不讀取，
  且 `video_queue_settings` 沒有 NOTIFY trigger，送出會是不誠實的過期值）。5 分鐘 hard lease、15 秒
  heartbeat、429 容量上限，行為與 Live Display stream 一致；詳見
  [docs/guides/cloudflare-pages.md](../guides/cloudflare-pages.md)。
- `GET /api/video-queue/public/{username}` 維持匿名唯讀；`POST .../advance` 與
  `PATCH .../entries/{id}/metadata`、`POST .../entries/{id}/playback-started` 必須帶
  `X-Overlay-Key` capability。播放開始只接受 `confirmed`／`best_effort`，同一 entry 重送不重複計次；
  dashboard preview 永不 mutation，登入 dashboard 改走 `POST /api/video-queue/advance`。`stream` 只取代狀態輪詢。
- `GET /api/video-queue/public/{username}/entries/{id}/clip-source`（無需認證、rate-limited、
  scoped 到該頻道佇列裡的 `twitch_clip` entry）：回 `{url}` — Twitch clip 的簽章直連 MP4，讓 overlay
  用 `<video>` 播（embed iframe 在 OBS 無法 autoplay）。走 Twitch 私有 GraphQL（`ShareClipRenderStatus`，
  非官方、Bilibili-tier 依賴，token 現拿不存）；失敗回 404，overlay fallback 回 iframe。
  詳見 [docs/architecture/video-queue-platforms.md](../architecture/video-queue-platforms.md)。
- `GET /api/video-queue/public/{username}/entries/{id}/reel-source`（匿名、rate-limited、頻道與 entry scoped）：
  透過 InstaFix 即時解析 Instagram Reel 簽章 MP4；失敗回 404，overlay 直接略過（Instagram 無 embed fallback）。
- `GET /api/video-queue/history?limit=&cursor=`（`require_activated`，租戶自身頻道）：已播／已略過的
  entry，`ended_at` 由新到舊，keyset 分頁——`cursor` 帶上一頁最後一列的 `ended_at` ISO 字串，
  `next_cursor` 為 `null` 代表沒有更多。無新表，紀錄一直是留在 `video_queue` 裡的 terminal row，
  只是之前沒有讀取路徑；`idx_video_queue_channel_ended`（migration 107）建索引，超過 30 天由
  `video_queue_history_retention_loop`（`api/app.py` lifespan，每日）刪除。
- `GET /api/video-queue/rankings?scope=channel|global&days=7|30&video_type=`
  （`require_activated`、`private, no-store`）：回傳有效播放的匿名彙總；本台依播放次數排序，全站先依不同
  頻道數、再依播放次數排序。回應不含 contributing channel 或點播者 identity，另帶目前租戶自己的
  `active_status`／`blocked_kind` 供操作按鈕使用。
- `GET`／`PUT /api/video-queue/settings` 回傳／更新全域規則；`max_duration_seconds` 套用 Chat、點數兌換、
  Donate 與 dashboard，並與點數的 `max_duration_redemption` 取較嚴者。容量、最低觀看數與
  `replay_cooldown_hours` 套用 Chat、點數與 Donate；dashboard 是 broadcaster override。重複與重播 identity
  使用 `(video_type, video_id)`。`volume_percent`（0–100，migration 133）套用可控播放器；嵌入式 fallback
  只支援靜音。設定回應為 `private, no-store`。
- `POST /api/video-queue/settings/rotate-key`（登入且 `X-Niibot-Action: video-queue`）輪替 OBS capability，
  舊 URL 立即失效（migration 132）。
- `GET`／`POST /api/video-queue/blocklist`、`DELETE /api/video-queue/blocklist/{id}`
  （`require_activated`，租戶自身頻道）：Video Queue 封鎖清單（`video_queue_blocklist`，migration 110）。
  `kind`：`video`（video_id）／`creator`（平台原生 creator_id）／`keyword`（標題不分大小寫子字串）／
  `user`（`requested_by_id` 優先，否則小寫 login）。四條加入路徑 insert 前呼叫
  `VideoQueueBlocklistRepository.check`（per-channel 30s TTL 快取，Python 比對）；Donate 無穩定 Twitch
  user identity，因此 `user` 規則只套用 Chat／點數兌換。
  命中時 API 回 `VIDEO_QUEUE.BLOCKED`（422），chat／兌換回中文訊息。migration 135 起 `video`／
  `creator` 可帶 `video_type`，`POST` 對 `(channel, kind, lower(value), COALESCE(video_type, '*'))`
  idempotent；既有 `video_type IS NULL` 規則保留跨平台 wildcard 語意，keyword／user 不接受 provider。

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
  以及 `reply_delay_seconds`（聊天回覆延遲秒數，補償 Twitch 廣播延遲，範圍 0–30，預設 5）。
- `PATCH /api/checkin/settings`：部分更新上述欄位；body 嚴格禁止 `channel_id` 與未知欄位，mutation 必須帶
  `X-Niibot-Action: checkin-settings`。
- `GET /api/checkin/collections`：讀取第一個有圖 catalog、目前抽卡範圍與全部 7 個 set／48 張卡片資料。
- `PATCH /api/checkin/collections`：body 只接受 nullable `set_key`；`null` 使用包含全部卡片的官方 fallback，
  其餘值只可指向已發布的官方單一 set pool。mutation 必須帶 `X-Niibot-Action: checkin-collections`。

模板只接受 `$(@user)`、`$(user)`、`$(count)`、`$(streak)`、`$(today_order)`、`$(date)`；server 會同時驗證
未知變數與 Twitch 500 字元的最壞輸出長度。`$(count)` 包含 carry-over，`$(streak)` 可接續匯入紀錄；
`$(today_order)` 是頻道當地日期內的穩定簽到順序。聊天指令與 Channel Points `checkin` adapter 共用同一份 tenant 設定。
只有確實建立 check-in、draw 與 Overlay event 的 `recorded` 結果套用 reply delay；`duplicate` 沒有 draw／event
且立即回覆。延遲是 in-process best-effort 校準，不等待或要求 Overlay ACK；OBS 離線也不會回滾已提交資料。
前端 `/events` 只管理 EventSub 回覆；`/channel-points` 管理 reward → action 映射，並由每日簽到列開啟
獨立的 `Check-in settings` 編輯面。`Community Overlay` 只顯示目前 reward 綁定摘要並導向
`/channel-points`，不提供第二個 mutation 入口。

### Daily Check-in carry-over import

- `POST /api/checkin/import/summary/columns`：owner-only multipart 欄位檢查。接受一個 upload 或公開
  Google Sheets URL，只回傳 bounded headers、格式、工作表名稱與 exact-alias 建議 mapping；不解析 Twitch
  身份、不保存原始內容。
- `POST /api/checkin/import/summary/preview`：owner-only multipart preview。接受一個 `.csv`、`.tsv`、`.xlsx`
  upload，或一個可匿名讀取的 Google Sheets URL；另帶 source slug、IANA source timezone 與 through date。
  可帶 `column_mapping` JSON，以 canonical field → zero-based source column index 手動覆寫欄位對應；回傳
  stable Twitch identity、逐列狀態及預設選取，不保存原始輸入。
- `POST /api/checkin/import/apply`：owner-only、all-or-nothing apply。body 帶 `import_id`、`selected_keys` 與
  `old_source_disabled: true`；相同 content／selection／policy 具 idempotency，不會重複加總。

三個 POST 都要求 `X-Niibot-Action: checkin-import`。第一版若同一 stable viewer 已有任何 Niibot ledger
或 carry-over，整批回 `409 CHECKIN_IMPORT.CONFLICT`；不提供 sum、max 或 overwrite。

### Daily Check-in data management

- `GET /api/checkin/data/summary`：owner-only，回傳匯入承接值與完整簽到資料兩種清除範圍的影響數量，
  以及 destructive confirmation 使用的頻道名稱。
- `GET /api/checkin/data/export`：owner-only，下載 UTF-8 BOM CSV。欄位固定為 `Username`、
  `Twitch User ID`、`DisplayName`、`Count`、`LastDate`、`Streak`、`TodayOrder`，可直接走同一個
  carry-over importer。文字欄位會防止試算表公式執行；回應為 `private, no-store`。
- `POST /api/checkin/data/clear`：owner-only，body 只接受 `scope: imported | all` 與頻道名稱確認字串，
  並要求 `X-Niibot-Action: checkin-data`。`imported` 只撤銷 carry-over/import batch 並依真實 ledger
  重算 streak；`all` 另清除簽到 ledger、對應收藏卡及 `checkin.recorded` 畫面事件。兩者都保留時區、
  回覆模板、reward mapping 與收藏卡池設定，並在同一交易寫入 tenant audit event。

匯出是跨 Bot 可攜的「每位觀眾彙總」，不是 lossless 備份；它不包含逐日簽到歷史、抽卡結果或 Overlay
事件。完整清除以前應先下載 CSV。清除與即時簽到／匯入共用 channel advisory lock，避免 cutover 競爭。

## 租戶邊界

`channels_router` 與 `commands_router` 的 channel-scoped 端點已改用
`require_tenant_access` / `require_self_tenant_access` 依賴，其餘 router 仍走 legacy 的
`get_current_channel_id` shim。遷移進度與設計見
[architecture/admission-and-tenancy.md](../architecture/admission-and-tenancy.md)。
