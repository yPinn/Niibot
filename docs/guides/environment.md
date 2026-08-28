# 環境變數

所有 env 檔案的唯一總表。每個 `*.env` 都有對應的 `*.env.example` 範本；
`bash scripts/env.sh init` 會一次複製全部（見 [development.md](development.md)）。

一律不提交任何 `.env`。中括號註記：`(選用)` 可留空、`(dev)` 僅本機直跑時需要。

## 本機／正式共用檔

### `.env`（repo 根）

Docker Compose 變數替換用。

| 變數                                                  | 說明                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------ |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | Postgres 容器初始帳密                                              |
| `DOCKER_DATABASE_URL`                                 | 容器內連線字串，格式 `postgresql://USER:PASSWORD@postgres:5432/DB` |

### `backend/shared.env`

api、twitch-bot、discord-bot 三服務共用。

| 變數                                        | 說明                                                                      |
| ------------------------------------------- | ------------------------------------------------------------------------- |
| `DATABASE_URL`                              | 本機直跑時的連線字串（Docker 內由 `DOCKER_DATABASE_URL` 覆蓋）            |
| `FRONTEND_URL`                              | OAuth redirect origin 與 CORS allow-list                                  |
| `TWITCH_CLIENT_ID` / `TWITCH_CLIENT_SECRET` | Twitch App 憑證（[dev.twitch.tv/console](https://dev.twitch.tv/console)） |
| `BOT_ID` / `OWNER_ID`                       | Bot 與擁有者的 Twitch user ID                                             |
| `GROQ_API_KEY` / `GROQ_MODEL`               | AI provider（速度優先，Twitch 預設首選）                                  |
| `GEMINI_API_KEY` / `GEMINI_MODEL`           | AI provider（AI Studio key，非 GCP service account）                      |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL`   | AI provider（free-tier 備援）                                             |
| `YOUTUBE_API_KEY`                           | 影片佇列查片長／觀看數                                                    |
| `ERROR_WEBHOOK_URL`                         | (選用) ERROR 以上 log 推送的 Discord webhook                              |

> 至少設定一組 AI key；空的 key 會被自動跳過。優先序見
> [architecture/overview.md](../architecture/overview.md) 的 AI Provider 鏈一節。

### `backend/api/.env`

| 變數                     | 說明                                                                    |
| ------------------------ | ----------------------------------------------------------------------- |
| `JWT_SECRET_KEY`         | JWT 簽章密鑰（`secrets.token_urlsafe(32)`）                             |
| `JWT_ALGORITHM`          | (選用) 預設 `HS256`                                                     |
| `JWT_EXPIRE_DAYS`        | (選用) 預設 `7`                                                         |
| `PAYMENT_ENCRYPTION_KEY` | 金流設定加密（Fernet key）                                              |
| `API_URL`                | 對外 URL，用於 OAuth redirect 與 webhook callback                       |
| `ENVIRONMENT`            | `production` / `development`                                            |
| `RELEASES_GITHUB_TOKEN`  | (選用) 讀 private repo release，`read:contents` scope                   |
| `DISCORD_PUBLIC_KEY`     | Discord 互動 webhook 簽章驗證（Developer Portal → General Information） |
| `ERROR_WEBHOOK_URL`      | (選用) 同上                                                             |

### `backend/twitch/.env`

App 憑證與 `BOT_ID` / `OWNER_ID` 走 `shared.env`。

| 變數                | 說明                             |
| ------------------- | -------------------------------- |
| `CONDUIT_ID`        | (選用) 重用既有 EventSub conduit |
| `ERROR_WEBHOOK_URL` | (選用) 同上                      |
| `PORT`              | (dev) health server，預設 `4344` |

### `backend/discord/.env`

App 憑證走 `shared.env`。

| 變數                    | 說明                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------- |
| `DISCORD_BOT_TOKEN`     | Bot token                                                                                          |
| `DISCORD_STATUS`        | `online` / `idle` / `dnd` / `invisible`                                                            |
| `DISCORD_ACTIVITY_TYPE` | `playing` / `listening` / `watching` / `competing` / `streaming` / `custom`                        |
| `DISCORD_ACTIVITY_NAME` | 狀態文字                                                                                           |
| `DISCORD_ACTIVITY_URL`  | (選用) `streaming` 型態限定，須為 twitch.tv URL                                                    |
| `DISCORD_DESCRIPTION`   | (選用) 覆蓋 Developer Portal 的 bio，上限 400 字                                                   |
| `INSTAGRAM_SESSION_ID`  | (選用) Instagram 個人頁 embed，約 90 天效期                                                        |
| `INSTAFIX_HOST`         | (dev) Instagram OG proxy，Docker 由 compose 設定                                                   |
| `SCRAPLING_HOST`        | (選用) Threads sidecar；空值＝停用（見 [integrations/scrapling.md](../integrations/scrapling.md)） |
| `DISCORD_SYNC_COMMANDS` | (選用) 增改 slash command 後設一次 `true`                                                          |
| `DISCORD_GUILD_ID`      | (選用) 指定 guild 同步，較快                                                                       |
| `ERROR_WEBHOOK_URL`     | (選用) 同上                                                                                        |
| `PORT`                  | (dev) health server，預設 `8080`                                                                   |

### `backend/scrapling/.env`

| 變數                 | 說明                                            |
| -------------------- | ----------------------------------------------- |
| `THREADS_SESSION_ID` | threads.com 的 `sessionid` cookie，約 90 天效期 |
| `PORT`               | 預設 `3001`                                     |
| `ENVIRONMENT`        | `production` 才啟用 `ERROR_WEBHOOK_URL`         |
| `LOG_LEVEL`          | 預設 `INFO`                                     |
| `ERROR_WEBHOOK_URL`  | (選用) 同上                                     |

### `frontend/.env`

| 變數                          | 說明                                                      |
| ----------------------------- | --------------------------------------------------------- |
| `VITE_BOT_USERNAME`           | Bot 帳號名，抑制自身的「授予 Mod」提示                    |
| `VITE_DISCORD_COMMUNITY_URL`  | Discord 社群邀請連結（側欄／說明橫幅／條款頁）            |
| `VITE_DISCORD_BOT_INVITE_URL` | 把 Bot 加入自己伺服器的 OAuth 連結                        |
| `VITE_SUPPORT_ECPAY_URL`      | 贊助頁 ECPay 連結                                         |
| `VITE_ENVIRONMENT`            | (選用) `production` 鎖定 WIP 頁面；`staging` / `dev` 不鎖 |
| `VITE_API_URL`                | (dev) 開發伺服器代理目標；正式部署不設                    |

Cloudflare Pages 另需在專案設定中加 `API_BACKEND`（後端位址，由 Cloudflare Tunnel 提供）。

## Staging

`scripts/env.sh` 另管理一組 staging 檔案：`.env.staging`、`backend/shared.staging.env`、
`backend/{api,twitch,discord,scrapling}/.env.staging`。內容鍵值與上表相同，值指向 staging 資源。

本機開發可建 `backend/shared.env.local`（gitignored）覆蓋 `shared.env` 的個別值。

## CI/CD

GitHub Actions 部署所需的密鑰與變數放在 `.github/secrets/{base,prod,staging}.env`
與 `.github/variables/{base,prod,staging}.env`，用 `.github/push.sh` / `pull.sh` 與 GitHub 同步。
詳見 [deployment.md](deployment.md)。
