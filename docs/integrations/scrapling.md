# Scrapling — Threads 抓取 sidecar

## 這是什麼

`backend/scrapling/` 是一個獨立的 FastAPI 服務，用登入狀態的 Playwright／Chromium
（含 stealth patch）抓 Threads 貼文與個人頁。Threads 內容由 JS 算圖，OG 標籤幾乎空白，
一般 crawler 抓不到 caption 與媒體，所以 discord bot 的 social preview 走這個 sidecar 補資料。

底層是 `scrapling` 套件（見 `backend/scrapling/pyproject.toml`）。服務名稱涵蓋
Instagram／Threads，但目前只實作 Threads 端點。

## 端點

| 端點                                    | 說明                                                                  |
| --------------------------------------- | --------------------------------------------------------------------- |
| `GET /threads?url=<貼文網址>`           | 回傳 `caption`、`like_count` 等互動數、`image_urls[]`、`video_urls[]` |
| `GET /threads/profile?url=<個人頁網址>` | 回傳 `bio`、`followers`、`recent_views`                               |
| `GET /health`                           | `{"status": "ok"}`                                                    |

錯誤碼：`422` 網址格式不符、`503` 瀏覽器尚未就緒、`500` 其他。
偵測到導向登入頁時回傳空 caption 並記 warning——通常代表 `THREADS_SESSION_ID` 過期。

## 設定

| 位置                     | 變數                 | 說明                                                                  |
| ------------------------ | -------------------- | --------------------------------------------------------------------- |
| `backend/scrapling/.env` | `THREADS_SESSION_ID` | threads.com → F12 → Application → Cookies → `sessionid`，約 90 天效期 |
| `backend/scrapling/.env` | `PORT`               | 預設 `3001`                                                           |
| `backend/discord/.env`   | `SCRAPLING_HOST`     | sidecar 位址（如 `scrapling:3001`）；**留空＝停用**                   |

`SCRAPLING_HOST` 未設時，discord 的 Threads 處理只用 OG scrape，embed 會缺 caption／媒體，
並記一行 warning。呼叫端在
[social_preview/cog.py](../../backend/discord/cogs/social_preview/cog.py) 的 `_fetch_scrapling`。

## 部署現況

這個服務**目前不在 `docker-compose.yml` 也不在 CI 部署流程中**：

- 有 `backend/scrapling/Dockerfile`（uv + `playwright install chromium`）與 `uv.lock`。
- dependabot 有監控 `/backend/scrapling` 的相依套件。
- 但沒有 compose service，也沒有 `deploy-*.yml` 的建置步驟——需要用時自行 `docker build` 並
  獨立啟動，再把 `SCRAPLING_HOST` 指過去。

Cookie 會持久化到容器內 `/app/cookies.json`（`COOKIES_PATH`），讓 session 撐久一點；
要跨重啟保留就掛 volume。
