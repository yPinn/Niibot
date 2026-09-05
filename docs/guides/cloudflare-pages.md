# Cloudflare Pages Functions 操作規範

Niibot 前端部署於 Cloudflare Pages，`/api/*`、`/health` 與其他少數動態路徑由 Pages Functions
代理到後端。本文件固定免費額度、路由邊界、故障行為與常駐 Overlay 的 request budget。

最後核對 Cloudflare 官方文件：2026-09-02。

## Free plan 限制

- Workers Free plan 每個帳戶每日合計 100,000 requests，Pages Functions 與同帳戶 Workers 共用額度。
- 每日額度於 00:00 UTC 重置，即台灣時間 08:00。
- Pages Functions invocation 會計入 Workers request；未觸發 Function 的靜態資產請求免費且不限量。
- Free plan 每次 HTTP invocation 的 CPU time 上限是 10 ms；等待網路 I/O 不計入 CPU time。
- HTTP-triggered Worker 沒有固定 wall-clock duration 上限；只要 client 保持連線，就能串流 response
  與維持上游 subrequest。Cloudflare runtime 更新時，既有 request 只有 30 秒 grace period，因此 client
  必須能安全 reconnect。
- 每個 Free invocation 最多 50 個外部 subrequests。Niibot API proxy 每個 invocation 預期只有一個
  backend `fetch()`。

官方依據：

- [Pages Functions pricing](https://developers.cloudflare.com/pages/functions/pricing/)
- [Workers limits](https://developers.cloudflare.com/workers/platform/limits/)
- [Workers pricing](https://developers.cloudflare.com/workers/platform/pricing/)

## Functions invocation routes

Pages project 只要偵測到 `functions/`，若沒有明確 `_routes.json`，所有路徑可能預設觸發 Function。
Vite build 必須把
[`frontend/public/_routes.json`](../../frontend/public/_routes.json)
複製到 `dist/_routes.json`，並只 include 確實需要動態處理的路徑。

目前契約：

```json
{
  "version": 1,
  "include": [
    "/api/*",
    "/health",
    "/status",
    "/donate/*",
    "/*/commands",
    "/*/crosshairs"
  ],
  "exclude": []
}
```

- `/api/*`、`/health`、`/status` 代理後端。
- 公開 donate／commands／crosshairs 路徑只讓 crawler 經過動態 metadata middleware。
- JS、CSS、字型、圖片與一般 SPA navigation 不得觸發 Functions。
- 修改 Functions 或 build output 時，CI／部署驗證必須直接檢查
  `dist/_routes.json`，不能只確認 source file。

官方依據：[Pages Functions routing](https://developers.cloudflare.com/pages/functions/routing/)。

## Fail open 與 Fail closed

- **Fail open**：額度耗盡後跳過 Function，繼續提供靜態資產。對 `/api/*` 而言，SPA fallback 可能回傳
  `200 text/html`，前端若直接解析 JSON 會出現 `Unexpected token '<'`。
- **Fail closed**：額度耗盡後回 Cloudflare 1027 error，不會把 API failure
  偽裝成 SPA HTML；但整個 Pages project 的受保護路徑會明確中斷。

認證與 API proxy 是關鍵功能，正式環境原則上應採 Fail closed，讓監控與 client 收到真正錯誤。切換設定前
必須先在 staging 驗證 error UX 與 rollback；Fail mode 不會降低 request 數量，也不會恢復已耗盡額度。

## Overlay request budget

常駐 OBS Browser Source 以 24 小時運作計算。每個 polling endpoint 的每日請求量為：

```text
requests_per_day = 86,400,000 ms / interval_ms
```

### 事故前

| Source                    | Interval | Endpoints | Requests/day |
| ------------------------- | -------: | --------: | -----------: |
| Live Display events       |      1 s |         1 |       86,400 |
| Live Display themes       |      5 s |         2 |       34,560 |
| Video Queue Overlay state |      3 s |         1 |       28,800 |
| Game Queue Overlay state  |     10 s |         1 |        8,640 |
| **合計**                  |          |           |  **158,400** |

單一 Live Display 已達 120,960 requests/day，必然超過 Free plan；三種常駐 source 合計超額 58%。

### Production hotfix budget

| Source                    | Interval | Endpoints | Requests/day |
| ------------------------- | -------: | --------: | -----------: |
| Live Display events       |      5 s |         1 |       17,280 |
| Live Display themes       |     60 s |         2 |        2,880 |
| Video Queue Overlay state |     10 s |         1 |        8,640 |
| Game Queue Overlay state  |     30 s |         1 |        2,880 |
| **合計**                  |          |           |   **31,680** |

這是每種 source 各開一份時的暫時止血預算，比事故前降低 80%。同一 source 開多份會線性增加用量；40,000/day
是 CI contract，不是長期 transport 目標。Dashboard、登入與其他 API 仍需保留額度，因此不得把 100,000 全部分配給
Overlay。

長期方案是 durable event table replay + PostgreSQL `NOTIFY` 喚醒 SSE；
events 與 theme 共用可重連 stream，移除秒級 polling；正常穩態僅保留每 5 分鐘一次的 bounded
stream rotation（每個常駐 source 約 288 requests／日）。

### Live Display stream contract

- Renderer 以 `GET /api/live-display/public/stream` 建立一條 `fetch` stream，
  capability 僅放在 `X-Overlay-Key`，不得放進 query、log 或 SSE payload。
- 初次 live 連線不重播舊事件；preview 使用 `after_id=0`。斷線後必須帶最後收到的 cursor，
  由 `community_overlay_events` 補送尚未過期事件。
- PostgreSQL `NOTIFY` 只包含 `channel_id` 與更新種類，僅作喚醒；事件與 theme body 一律重新由
  durable tables 讀取。每個 API process 只能有一條 listener connection，不得為每個 OBS source
  配一條資料庫連線；每個 channel 最多 10 條、每個 process 最多 1,000 條 concurrent streams，
  超限明確回 429。
- Pages proxy 只對上述精確 GET route 取消 15 秒上游 timeout，並組合 caller abort signal 與 5 分鐘
  stream lease；其他 `/api/*` 仍維持 15 秒 timeout。response 必須保持 streaming，不得先 buffer
  完整 body。lease 到期由 renderer 帶 cursor 重連，每個常駐 source 最多約 288 次 invocation／日，
  backend generator 也實施相同的 monotonic hard lease，因此即使 Cloudflare 未送出 disconnect signal，
  殘留 upstream／hub slot 仍由 API 自己在 5 分鐘內清除。
- Preview 與 Production 建議啟用 Pages Functions `enable_request_signal` 相容性旗標，讓 client／OBS
  中斷後能立刻取消 upstream fetch；它是快速清理優化，不是容量正確性的唯一保證。若 Dashboard
  未列出該旗標，應透過先下載並完整核對的 Wrangler config 或 Pages API 管理；不要直接加入不完整
  設定覆蓋既有環境變數或 bindings。staging 仍需驗證 client abort 與 hard lease 兩條 cleanup 路徑。
- SSE 使用 `snapshot`、`update`、`heartbeat`；renderer 必須隔離壞 frame、依 event id 去重，並以
  指數退避加 jitter reconnect。正常狀態不得 fallback 到週期 polling，避免故障時靜默恢復高流量。
- Cloudflare runtime 更新或 hard lease 會中止長連線，因此「任一時刻一條 invocation」不代表
  永不重連；驗收看的是 invocation 不再以秒級 polling 線性成長，且重連能以 cursor 補齊事件。
- Dashboard 測試預覽（`&block=<type>`）是前端專用的本地過濾參數，不改變上述後端 API／查詢契約——
  伺服器仍回傳整個 channel 的事件，只是 renderer 端多丟掉不符 block type 的事件。這條測試連線也不會
  無限期占用前述的 per-channel／per-process 併發串流額度：Dashboard 觸發測試動畫後，會依已發布主題的
  `display_ms` 自動在動畫播完後不久關閉該連線，不需要使用者手動操作。

官方依據：

- [Request signal compatibility flag](https://developers.cloudflare.com/changelog/post/2025-05-22-handle-request-cancellation/)
- [Pages Wrangler configuration](https://developers.cloudflare.com/pages/functions/wrangler-configuration/)

## Incident 檢查順序

當 `/api/*` 回 HTML、登入失敗或 Function 流量異常時：

1. 直連 backend endpoint，確認 status 與 `Content-Type`。
2. 檢查 deployment build log 是否編譯／上傳 Functions 與 `_routes.json`。
3. 檢查實際 invocation routes，不以 repository source 代替部署 artifact。
4. 對 Functions live logs 發送帶唯一 query 的 request，確認 Worker 是否真的收到。
5. 檢查 account-level Workers requests、當日 UTC window 與 Fail mode。
6. 用 Web Analytics visits 對照 HTTP requests，並依 country、時間斜率判斷
   人流、crawler 或常駐 client。
7. 量測修正後至少 15 分鐘的 requests slope；只有斜率下降才算止血成功。

## 本次 incident 基準

2026-09-02 調查到過去 24 小時約 179.9k HTTP requests，其中 179,504 來自台灣；Web Analytics 同期只有
5 visits／154 pageviews。平均約 2.08 requests/second，與本地長時間開啟的
OBS Browser Source polling 相符，不符合一般訪客或全球 crawler 分布。

部署降低 polling 只影響後續 request slope，不能重置已耗盡額度。若正式站需要在重置前立即恢復，只有：

- 經帳戶擁有者授權後升級 Workers Paid；或
- 等待 00:00 UTC（台灣時間 08:00）自動重置。

重新部署、調整 `_routes.json` 或切換 Fail mode都不會補回當日 quota。
