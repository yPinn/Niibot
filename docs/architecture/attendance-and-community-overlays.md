# 出席與 Live Display 架構

本文件界定既有觀看分析、`!簽到` 與社群 Overlay 的資料責任。核心原則是：
**同屬 Attendance domain，但不同事實不可共用計數或 streak。**

## 三個邊界

| 子系統                                 | 事實粒度                       | 主要用途                         | 不可混入                  |
| -------------------------------------- | ------------------------------ | -------------------------------- | ------------------------- |
| Session Attendance                     | 每頻道、每場直播、每位觀眾     | 後台觀看分析、活躍分數、忠誠分層 | 每日主動簽到次數          |
| Daily Check-in                         | 每頻道、每個當地日、每位使用者 | 社群持續參與、活動與獎勵         | 被動觀看時數／場次 streak |
| Live Display（內部 Community Overlay） | 每頻道、每個已發生的視覺事件   | OBS 動畫與活動回饋               | feature 的權威狀態        |

所有資料與查詢皆以 `channel_id` 作為 tenant key。同一 Twitch 使用者在不同頻道的
觀看、簽到、活動進度與 Overlay feed 完全隔離。

## Session Attendance：可信度先於推論

目前 Twitch Bot 每分鐘完整讀取 `/helix/chat/chatters`，成功的 snapshot 才能同時：

1. 增加當下觀眾的 `watch_seconds`。
2. 增加該 `stream_sessions.attendance_snapshot_count`。
3. 讓該場成為 attendance streak 的 eligible session。

下列情況一律視為「未知」，不可推論所有人缺席：

- 只由 VOD 匯入，Bot 未實際觀測的場次。
- 缺少 bot token、Twitch API 失敗或分頁未完整取得。
- Bot 異常停止且整場沒有任何成功 snapshot。

成功取得的空聊天室仍是完整觀測，因此該場 eligible，並可正確中斷上一場觀眾的 streak。
stale session 若曾有完整 snapshot，補關閉時仍需按時間順序結算；未觀測的 stale session 則略過。

`viewer_attendance_streaks` 僅代表「連續 eligible 直播場次」。`current_streak` 可歸零，
`best_streak` 是歷史最高值；兩者都不代表每日簽到。

## Daily Check-in：獨立 ledger

`!checkin`／`!簽到` 以不可變 ledger 記錄成功日期，唯一鍵為
`(channel_id, user_id, checkin_date)`，由資料庫保證同一頻道每日只成功一次。
累積 `count` 定義為該頻道的成功簽到天數；current／best daily streak 是可重算 projection。

頻道 timezone、成功／已簽到模板與活動卡設定屬於 channel-scoped config。
成功簽到可選擇性關聯當下 `session_id`，但不得改寫 Session Attendance、觀看分數或忠誠分層。

### 觸發方式：聊天指令與 Twitch 頻道點數

`!checkin`／`!簽到` 與 Twitch 自訂獎勵兌換都是 Daily Check-in 的 adapter，共用同一個
`AttendanceService`、頻道 timezone、每日唯一鍵、回覆模板與成功 Overlay transaction。兩種入口可同時啟用；
同一使用者同日從任一入口成功後，另一入口只會得到 duplicate 結果，不會增加 count 或再次發 Overlay。

頻道點數採平台管理、Niibot 唯讀的權限模型：實況主在 Twitch 建立獎勵並設定成本、每人每場上限、
全頻道單場上限與是否略過請求佇列；Niibot 只以 `channel:read:redemptions` 讀取並監聽，不要求
`channel:manage:redemptions`，也不建立、修改、完成、取消或退款獎勵。設定以 Twitch `reward_id` 穩定綁定；
舊資料僅在尚未有 id 時保留精確名稱相容比對，已綁定 id 的資料不得退回名稱模糊比對。

建議獎勵為 10 點、每人每場 1 次並略過請求佇列；全頻道單場上限由租戶依活動規模設定。
Twitch 的 per-stream 限制與 Daily Check-in 的當地日不同步，因此同日跨場仍可能重複花費點數。
在最小權限模式下 Niibot 無法退款，後台必須持續揭露此限制。

## Live Display：共用頁面，block 各自持有契約

簽到、投票、抽獎、共同目標等功能各自維護規則與權威資料；成功 transaction 另寫一筆
`community_overlay_events`。事件包含單調遞增 id、`channel_id`、event type、schema version、
actor snapshot、validated payload、發生／到期時間與 idempotency key。

同一個 Live Display 頁面可以承載多個 block，例如每日簽到、運勢或塔羅；每個 block 在 registry 定義
自己的 `block_type`、renderer、schema、預設外觀、驗證器與測試事件。新增 block 不得沿用或覆蓋其他
block 的外觀欄位。Overlay runtime 只負責依 cursor 讀取、排序、去重、排隊與 renderer dispatch，不回查 feature table，
也不執行 payload 內的 HTML／CSS／JS。第一版可短輪詢；需要更低延遲時，以 durable table replay +
PostgreSQL `NOTIFY` 喚醒 SSE，維持同一事件契約。

Game Queue 與 Video Queue 是長時間存在的狀態／播放器，不塞入短事件 feed；未來只共用
Overlay shell、公開金鑰、theme 與 transport primitives。

### 租戶樣式與發布模型

Live Display 樣式以 `(channel_id, block_type)` 隔離。後台編輯的是該 block 的 `draft_theme`，OBS 公開端點以
`block_type` 只讀對應的
`published_revision_id` 指向的不可變 revision；儲存草稿不會改動直播畫面，發布才會建立下一版快照。
重設草稿只複製目前已發布版本，不會刪除歷史 revision。每次草稿 mutation 都攜帶
`expected_draft_version`；舊分頁遇到版本不符回 409 並重新載入，避免覆蓋較新的草稿或發布錯誤快照。

目前 `checkin` block 的 schema v1 固定 renderer 為 `checkin-card`，只允許三個色票、四角位置、圓角、顯示秒數與動態強度；
server 與 client 都不接受任意 HTML、CSS 或 JavaScript。圖片資產與整包匯入／匯出留待後續版本，
屆時需先定義媒體儲存、掃描、配額與相容性契約，不能把外部 URL 或自訂程式碼直接塞入 theme JSON。

## 交付順序

1. 修正 Session Attendance observation completeness、stale close 與 streak eligibility。
2. 建立多租戶 Daily Check-in ledger、聊天回覆與設定。
3. 建立 durable community event feed 與 check-in 集點卡 renderer。
4. 第二種社群 activity 出現後，再抽取共用 activity service；不預先建立通用規則引擎。

## 已落地的 infra

- `viewer_checkins` 以 `(channel_id, user_id, checkin_date)` 保證每日一次；`checkin_settings`
  保存頻道 IANA timezone 與兩種聊天室模板。
- successful check-in 與 `checkin.recorded` event 在同一 transaction 寫入；duplicate 不發 event，
  optional `session_id` 會先驗證屬於相同 channel。
- `community_overlay_channels.public_key` 是可輪替 UUID capability；feed 初次只取得最新 cursor，
  增量讀取限制 100 筆、略過過期事件，並以每日 cleanup 刪除已過期視覺事件。
- `community_overlay_profiles` 以 `(channel_id, block_type)` 保存租戶草稿、draft version 與已發布指標；
  `community_overlay_revisions` 以相同範圍保存不可更新／刪除的發布快照，複合外鍵阻止 profile 指向其他
  頻道或其他 block 的 revision（migration 095／096／103）。
  直接刪除 revision 會被 trigger 拒絕；刪除整個 channel 時仍允許 FK cascade 清理該租戶資料（migration 097）。
- event type／schema version／renderer payload 經 shared catalog allowlist；feature ledger 不因視覺事件
  到期或清除而受影響。

## 目前可用鏈路

- `!checkin`／`!簽到` 走既有 builtin command guard；成功與同日重複都回傳該頻道累積天數，
  DB／模板錯誤只回覆一般失敗訊息，不記錄假成功 usage。
- Twitch Channel Points `checkin` action 以 `(channel_id, reward_id)` 找設定，收到兌換後走相同
  Attendance service；只有 `recorded` 會新增 Overlay event。Bot 不呼叫任何 reward mutation／退款 API。
- Dashboard 將三種責任分開：`/events` 只編輯 EventSub 回覆模板；`/channel-points` 是 reward → action
  映射的唯一寫入位置，並以獨立 `Check-in settings` sheet 編輯共用 timezone、成功與重複模板；
  `Live Display` 只呈現顯示內容、各 block 外觀、測試與 OBS 連結；簽到入口細節仍導向 `/channel-points`。
- 模板只允許 `$(@user)`、`$(user)`、`$(count)`、`$(date)`，renderer 不解譯 HTML、CSS、JS
  或通用 command substitution。
- OBS route 為 `/community-overlay#key=<uuid>`；capability 留在 URL fragment，不進入瀏覽器／CDN request log，
  前端以 `X-Overlay-Key` header 呼叫公開 API。正常啟動先取得 latest cursor、不重播歷史，之後每秒讀取
  增量 event，以 FIFO 播放 7 格循環集點卡；每 5 秒檢查 published revision，發布後不必重載 OBS。
- Dashboard 的 `Live Display` 頁位於相容路由 `/modules/community-overlay`，依「顯示內容、卡片樣式、
  預覽與測試、加入直播畫面」排序；每個 block 都提供不執行正式功能流程的測試動畫。頁面可啟停 feed、
  複製／輪替 capability URL、編輯／預覽／發布該 block 的頻道樣式；設定 mutation
  分別使用操作鎖，避免重複提交或舊 response 覆蓋新狀態。
- `/community-overlay#key=<uuid>&preview=1` 會從 cursor 0 讀取仍未過期事件，只供設定預覽／開發驗證。
- Vite development 另提供 `/dev/community-overlay` 隔離頁面預覽；production bundle 不包含此路由，
  正式 Dashboard 頁仍需登入並只存取目前租戶設定。
- `!ovltest [1-9999]` 僅在 `ENVIRONMENT=development` 且 chatter 就是該頻道 broadcaster 時生效；
  它只寫一筆 10 分鐘的 `system` preview event，不寫 `viewer_checkins`、不增加正式 count。
