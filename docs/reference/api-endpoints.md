# Dashboard API

FastAPI 服務（`backend/api/`）提供的路由前綴。開發環境互動式文件：`http://localhost:8000/docs`。

19 個 router 模組掛在 `backend/api/app.py`；前綴以各檔的 `APIRouter(prefix=...)` 為準。

| 前綴                     | Router                       | 功能                                                                               |
| ------------------------ | ---------------------------- | ---------------------------------------------------------------------------------- |
| `/api/auth`              | `auth_router`（掛在 `/api`） | Twitch OAuth、JWT cookie、用戶偏好                                                 |
| `/api/channels`          | `channels_router`            | 監控頻道管理、Bot 啟停                                                             |
| `/api/commands`          | `commands_router`            | 指令 CRUD、啟停、公開列表                                                          |
| `/api/events`            | `events_router`              | EventSub 事件設定、Channel Points 兌換                                             |
| `/api/analytics`         | `analytics_router`           | 場次分析、觀眾 Profile、熱門指令統計                                               |
| `/api/analytics/matcher` | `matcher_router`             | 頻道觀眾重疊分析                                                                   |
| `/api/stats`             | `stats_router`               | 頻道統計（top chatters／commands）                                                 |
| `/api/game-queue`        | `game_queue_router`          | 遊戲排隊                                                                           |
| `/api/video-queue`       | `video_queue_router`         | 影片佇列                                                                           |
| `/api/timers`            | `timers_router`              | 定時訊息 CRUD                                                                      |
| `/api/triggers`          | `message_triggers_router`    | 關鍵字觸發 CRUD                                                                    |
| `/api/crosshairs`        | `crosshairs_router`          | 準星管理、公開庫                                                                   |
| `/api/ai`                | `ai_settings_router`         | AI 助手設定（角色、enabled、cooldown、min_role、貼圖）                             |
| `/api/donate`            | `donation_router`            | 贊助結帳（ECPay／OPay／NewebPay／PayPal）、webhook                                 |
| `/api/payment-configs`   | `payment_config_router`      | 金流平台設定                                                                       |
| `/api/bots`              | `bots_router`                | Bot 狀態查詢                                                                       |
| `/api/discord`           | `discord_webhook_router`     | Discord 互動 webhook（slash command 簽章驗證）                                     |
| `/api/releases`          | `releases_router`            | 版本資訊查詢（`git describe`）                                                     |
| `/api/admin`             | `admin_router`               | 管理員工具（限 Owner）；聚合 `routers/admin/` 下 `logs`／`db`／`modules` 子 router |
| `/health`、`/status`     | —                            | 服務健康檢查                                                                       |

## 安全機制

| 項目         | 做法                                                            |
| ------------ | --------------------------------------------------------------- |
| Session      | JWT httponly cookie（HS256，預設 7 天，`JWT_EXPIRE_DAYS` 可調） |
| OAuth CSRF   | HMAC-SHA256 簽章的 state 參數                                   |
| 全域標頭     | CSP、HSTS 等安全標頭中介層                                      |
| 金流 webhook | 驗簽——CheckMacValue SHA-256、NewebPay AES-256-CBC + TradeSha    |

## 租戶邊界

`channels_router` 與 `commands_router` 的 channel-scoped 端點已改用
`require_tenant_access` / `require_self_tenant_access` 依賴，其餘 router 仍走 legacy 的
`get_current_channel_id` shim。遷移進度與設計見
[architecture/admission-and-tenancy.md](../architecture/admission-and-tenancy.md)。
