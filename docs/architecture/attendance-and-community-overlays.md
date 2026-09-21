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
累積 `count` 定義為該頻道的成功簽到天數加上已確認的外部 carry-over；`current_streak` 是可重算 projection。

頻道 timezone、成功／已簽到模板與活動卡設定屬於 channel-scoped config。
成功簽到可選擇性關聯當下 `session_id`，但不得改寫 Session Attendance、觀看分數或忠誠分層。

`checkin_settings.reply_delay_seconds`（預設 0，範圍 0–30）讓頻道自行延遲成功聊天回覆的送出時機：
聊天訊息走 IRC 幾乎即時，但 Live Display 動畫要透過 Twitch 廣播管線（編碼／CDN）才會出現在畫面上，
這段延遲因頻道的直播延遲模式而異，bot 無法查詢也無法控制。這個延遲只作用在 `recorded` 的「送出訊息」
動作；check-in ledger、抽卡與 Overlay event 維持立即原子提交。同日 `duplicate` 沒有動畫，因此立即回覆。
`!checkin` 與頻道點數兌換兩個入口都使用同一設定。

這項延遲只是 best-effort 的人工校準值，不是 Overlay 播放確認。系統不等待 OBS client ACK：OBS 可能離線、
同時開啟多個實例或只開 preview，而且 browser 開始播放仍不代表 Twitch 觀眾已看到該畫面。現行實作使用
in-process async delay；bot 若在等待期間重啟，可能漏送聊天回覆，但已提交的 check-in、draw 與 event 不會回滾或重抽。

### 觸發方式：聊天指令與 Twitch 頻道點數

`!checkin`／`!簽到` 與 Twitch 自訂獎勵兌換都是 Daily Check-in 的 adapter，共用同一個
`AttendanceService`、頻道 timezone、每日唯一鍵、回覆模板與成功 transaction。兩種入口可同時啟用；
同一使用者同日從任一入口成功後，另一入口只會得到 duplicate 結果，不會增加 count 或再次發 Overlay。

每筆 `recorded` check-in 恰好建立一筆 `viewer_card_draws`，並與 `viewer_checkins`、`community_overlay_events`
在同一個資料庫 transaction 寫入。抽卡失敗時整筆 transaction 回滾，不留下「簽到成功但沒有卡」的半成品；
duplicate 則不建立 draw 或 event。頻道尚未指定 pool 時使用已發布、不可變的官方 fallback pool。

### 舊 Bot 彙總資料轉移

後台可從 CSV、TSV、XLSX 或可匿名讀取的 Google Sheets 匯入每位觀眾的 aggregate summary。
所有格式先正規化為同一組欄位：`Username` 或 `Twitch User ID`、`Count`、`LastDate`，以及可選的
`DisplayName`、`Streak`、`TodayOrder`。系統先以 exact alias 建議對應，不使用模糊推測；使用者可在欄位
檢查步驟以來源 column index 手動 map canonical field，處理其他 Bot 的大小寫或自訂命名。Twitch login
會批次解析成 stable user id，找不到或與既有 Niibot ledger／carry-over 衝突的列不可套用。

外部 `Count` 寫入 `viewer_checkin_carryovers`，不展開成虛構 `viewer_checkins`，因此不補歷史卡片或
Overlay event。`$(count)` 與排行榜使用 carry-over + 真實 ledger；來源 streak 只作下一次簽到的 continuity
seed，隔日接續、日期 gap 歸 1。`$(today_order)` 在匯入截止日 duplicate 使用來源 `TodayOrder`；後續真實
簽到則以頻道 + 本地日期 advisory lock 序列化，再依 immutable ledger id 計算穩定的當日順序。來源沒有
`TodayOrder` 時，截止日 duplicate 明確代入 `0`，不虛構排序。

Preview 原始檔不落地；標準化結果只在綁定 user + tenant 的 10 分鐘記憶體 cache 中保存。Apply 僅限 owner、
要求 `X-Niibot-Action: checkin-import` 與「舊 Bot 已停用」確認，並以 channel advisory lock 與整批 transaction
阻止匯入 cutover 和即時簽到互相競爭。Google Sheets 只接受 HTTPS `docs.google.com/spreadsheets` 文件 URL，
由 server 重建固定 CSV export URL；只允許一次 HTTPS `doc-*-sheets.googleusercontent.com` 官方 export
redirect，其他 host、第二次 redirect、私人試算表 OAuth 與任意 URL 都不支援。

### 可攜匯出與資料清除

owner 可把 carry-over 與真實 ledger 合併匯出為 importer-compatible CSV。`Count` 是兩者加總，`LastDate`
取較新的來源日期，`TodayOrder` 必須跟該日期來自同一側；匯出不虛構逐日 ledger，也不包含收藏卡或 Overlay
event。因此 CSV 適合跨 Bot 移轉與重建 count/streak continuity，不是完整事件備份。

後台只提供一個「清除簽到資料」入口，確認對話框內有兩個 closed scope：`imported` 只移除 carry-over 與
import batch，保留 Niibot 後續 ledger/draw/event，再從 ledger 重建 streak；`all` 清除兩側簽到資料、
`checkin.recorded` event 與對應 `viewer_card_draws`。timezone、訊息模板、reward mapping、收藏 catalog/pool
都不在 reset 邊界。兩種操作都要求 owner、專用 action header、server-side impact summary、頻道名稱 typed
confirmation、rate limit、audit log，以及與 import/live check-in 相同的 exclusive advisory lock。

`viewer_card_draws` 平時仍為 immutable。完整清除利用 deferred check-in FK，先在同一交易刪除對應
`viewer_checkins`；migration 131 的 trigger 只在來源 check-in 已不存在時允許刪除該 draw。若任一步驟失敗，
deferred constraint 使整個清除交易回滾，不會留下半套資料。

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
也不執行 payload 內的 HTML／CSS／JS。傳輸層是 durable table replay + PostgreSQL `NOTIFY` 喚醒的 SSE
長連線，維持同一事件契約；`NOTIFY` payload 只帶 `channel_id` 作喚醒訊號，事件與 theme body 一律重新
由 durable table 讀取。

`checkin.recorded` 維持 `schema_version = 1`，並以 optional `payload.collection` 加入抽卡 snapshot。snapshot
已包含 draw／pool／algorithm、logical card 與 revision、set、rarity、artwork derivatives、`is_new`、
`copy_count` 與冊別進度，renderer 不必回查可變 catalog。這是相容性擴充：舊 OBS bundle 會忽略新增欄位；
新版遇到合法 snapshot 會顯示集卡冊，欄位缺漏或格式不合法則退回既有七格簽到卡，而不是丟棄整筆事件。

Game Queue 與 Video Queue 是長時間存在的狀態／播放器，不塞入短事件 feed。Video Queue 已遷移到
NOTIFY-woken SSE（`GET /api/video-queue/public/{username}/stream`），與 Live Display 共用同一個
process-level `NotifyWakeHub`（單一 LISTEN 連線監聽多個 notify channel），但狀態模型不同：
Video Queue 是單一目前快照覆蓋推送，沒有 cursor／事件回放。Game Queue 尚未遷移，未來要做時只共用
Overlay shell、公開金鑰、theme 與這組 transport primitives，不會複製一份獨立的 hub。細節見
[docs/guides/cloudflare-pages.md](../guides/cloudflare-pages.md) 的 Video Queue stream contract。

### 租戶樣式與發布模型

Live Display 樣式以 `(channel_id, block_type)` 隔離。後台編輯的是該 block 的 `draft_theme`，OBS 公開端點以
`block_type` 只讀對應的
`published_revision_id` 指向的不可變 revision；儲存草稿不會改動直播畫面，發布才會建立下一版快照。
重設草稿只複製目前已發布版本，不會刪除歷史 revision。每次草稿 mutation 都攜帶
`expected_draft_version`；舊分頁遇到版本不符回 409 並重新載入，避免覆蓋較新的草稿或發布錯誤快照。

目前 `checkin` block 的已發布 theme schema v1 仍固定 renderer id 為 `checkin-card`，只允許三個色票、四角位置、
圓角、顯示秒數與動態強度。event registry 依 optional collection snapshot 在同一個 block 內選擇集卡冊或 legacy
renderer，不需要遷移既有 theme revision。server 與 client 都不接受任意 HTML、CSS 或 JavaScript。
圖片資產與整包匯入／匯出留待後續版本，
屆時需先定義媒體儲存、掃描、配額與相容性契約，不能把外部 URL 或自訂程式碼直接塞入 theme JSON。
新 block 預設放在左下角，避開直播常見的右下視訊區；頻道仍可在四角位置中自行調整。一般 Live Display
新 profile 預設顯示 5 秒；既有已發布 revision 保留當時的 4 秒設定，不做破壞性改寫。`tarot` block 預設同為
5 秒、牌框圓角 16px。集卡冊把開書、印卡、入槽／重複合併、結果停留與關書限制在單一 5 秒 budget 內；
reduced-motion 或靜態編輯預覽直接呈現結果狀態。

### 簽到收藏與抽選模型

收藏核心與顯示主題分離；每次 draw 直接保存 card revision、pool revision、algorithm version 與 16-byte
entropy 對應的 rarity／card roll audit data，並透過不可變 references 固定 logical card、set 與 rarity revision。
Inventory 初期直接聚合 draw ledger，同一 logical card 可重複並累積 `copy_count`；新寫入路徑因此保證每筆
recorded check-in 對應一張 copy。冊別的 `total_cards` 隨已發布 set revision 固定，後續擴池以新 set／revision
表達，不讓既有冊別完成度倒退。既有歷史 check-in 必須另行執行 deterministic backfill；工具已提供，但不會
隨 migration 或服務啟動自動修改正式資料。

官方 starter pool 為原創「初途秘典」九張卡，rarity 採 common／rare／legendary，權重固定 70／25／5；
抽選演算法先依 rarity 權重選 bucket，再在該 bucket 內等機率選卡。catalog、rarity、set、card revision、
已發布 pool 與 draw audit 均由資料庫約束不可原地修改。Starter artwork 目前為空，renderer 使用內建原創符號
placeholder；租戶上傳、媒體處理、pool 管理 API 與動態素材仍是後續工作。

### 歷史簽到補卡

`backend/scripts/backfill_checkin_collections.py` 只補缺少 `viewer_card_draws` 的既有成功簽到，固定使用已發布的
`official-starter` revision 1，不讀取日後可能改變的 channel active pool 或 system fallback pointer。卡片選擇以
版本化 seed 加上 channel、viewer、簽到日期與 check-in id 產生 deterministic entropy；重跑不會換卡，也不建立
歷史 `community_overlay_events`。

CLI 預設為 report-only dry-run；寫入必須明確加上 `--apply`，且任何環境都需互動確認或 `--yes`，避免已注入的
`DATABASE_URL` 與 `--env` 標籤不同時繞過保護。作業依
channel、viewer、簽到日期、id 排序，以單一 viewer 為鎖定單位、可調 batch 大小分段 transaction。單一 batch
失敗會完整 rollback 並保留給下次續跑，最後回報 scanned、inserted、skipped、remaining 與 failures。正式 rollout
應先套用 migrations 112／113 並部署可讀 optional collection snapshot 的 frontend，再執行 dry-run、apply 與
`successful check-ins = draws = inventory copies` 對帳；此 repository 只交付工具，不代表已對正式環境執行。

### Viewer-isolated FIFO 播放

每個事件只代表一位 viewer 的獨立卡冊：完整開書、印卡、入槽或重複合併、關書後，FIFO 才播放下一筆。
不同 viewer 不會被合併成同一本 binder session。事件入列時會凍結當下已發布 theme，避免等待期間換版導致
動畫中途換皮；從 queue 推進下一筆前會再次檢查 `expires_at`，已過期事件直接略過，draw ledger 不受影響。

第一版刻意保留每筆約 5 秒的完整演出。尚未實作 queue ceiling、簽到摘要、跨 block 公平排程或 compact／parallel
模式；只有觀測到真實單頻道尖峰後才評估，而且任何後續壓縮仍須保持 viewer collection 隔離。

每日塔羅以 Twitch 使用者、UTC 日期與正規化主題組成 deterministic slot。未填主題使用綜合；綜合、感情、
事業與財運各自保存當天穩定結果，因此重複查詢同一主題不會重抽，不同主題則可得到不同牌面與對應牌義。
未知主題會回覆可用選項，不會靜默套用綜合。

## 交付順序

1. 修正 Session Attendance observation completeness、stale close 與 streak eligibility。
2. 建立多租戶 Daily Check-in ledger、聊天回覆與設定。
3. 建立 durable community event feed 與 check-in 集點卡 renderer。
4. 在相容的 v1 event 上加入原子抽卡與 viewer-isolated 集卡冊 renderer。
5. 交付固定首發卡池的 deterministic 歷史補卡工具，與 schema migration 分離且不補播 Overlay 事件。
6. 租戶上傳與 viewer collection surface 另案交付；第二種社群 activity 出現後再抽取共用
   activity service，不預先建立通用規則引擎。

## 已落地的 infra

- `viewer_checkins` 以 `(channel_id, user_id, checkin_date)` 保證每日一次；`checkin_settings`
  保存頻道 IANA timezone 與兩種聊天室模板。
- successful check-in、`viewer_card_draws` 與 `checkin.recorded` event 在同一 transaction 寫入；
  duplicate 不抽卡、不發 event 並立即回覆，optional `session_id` 會先驗證屬於相同 channel。
- migration 112 建立 immutable collection catalog、set／card／rarity revisions、published pool、fallback pointer
  與 draw audit ledger；migration 113 發布九張原創 starter cards 與 70／25／5 的官方 fallback pool。
- 歷史補卡 CLI 固定 official starter revision 1，支援 dry-run、bounded batch、production confirmation、失敗續跑
  與結束對帳；不建立歷史 Live Display event，且尚未對正式資料執行。
- `community_overlay_channels.public_key` 是可輪替 UUID capability；feed 初次只取得最新 cursor，
  增量讀取限制 100 筆、略過過期事件，並以每日 cleanup 刪除已過期視覺事件。
- `community_overlay_profiles` 以 `(channel_id, block_type)` 保存租戶草稿、draft version 與已發布指標；
  `community_overlay_revisions` 以相同範圍保存不可更新／刪除的發布快照，複合外鍵阻止 profile 指向其他
  頻道或其他 block 的 revision（migration 095／096／103）。
  直接刪除 revision 會被 trigger 拒絕；刪除整個 channel 時仍允許 FK cascade 清理該租戶資料（migration 097）。
- event type／schema version／renderer payload 經 shared catalog allowlist；feature ledger 不因視覺事件
  到期或清除而受影響。
- `checkin.recorded.v1` 的 collection snapshot 是 additive optional 欄位；舊 payload 或不合法 snapshot 仍由
  legacy renderer 顯示，避免前後端 staggered rollout 遺失事件。

## 目前可用鏈路

- `!checkin`／`!簽到` 走既有 builtin command guard；成功與同日重複都回傳該頻道累積天數，
  DB／模板錯誤只回覆一般失敗訊息，不記錄假成功 usage。
- `!rank`／`!排名` 讀取 Daily Check-in ledger 的累積簽到天數排名，與後台簽到排行榜共用同一段
  ranking SQL，兩者排序永遠一致；查無簽到紀錄時提示先簽到。Session Attendance 的
  `engagement_score`／`get_viewer_rank` 專供後台 Insights 分析頁使用，不再有聊天指令出口。
- Twitch Channel Points `checkin` action 以 `(channel_id, reward_id)` 找設定，收到兌換後走相同
  Attendance service；只有 `recorded` 會新增 Overlay event。Bot 不呼叫任何 reward mutation／退款 API。
- Dashboard 將三種責任分開：`/events` 只編輯 EventSub 回覆模板；`/channel-points` 是 reward → action
  映射的唯一寫入位置，並以獨立 `Check-in settings` sheet 編輯共用 timezone、成功與重複模板；
  `Live Display` 只呈現顯示內容、各 block 外觀、測試與 OBS 連結；簽到入口細節仍導向 `/channel-points`。
- 模板只允許 `$(@user)`、`$(user)`、`$(count)`、`$(streak)`、`$(today_order)`、`$(date)`，renderer 不解譯 HTML、CSS、JS
  或通用 command substitution。
- OBS route 為 `/live-display#key=<uuid>`；capability 留在 URL fragment，不進入瀏覽器／CDN request log，
  前端以 `X-Overlay-Key` header 對 `GET /api/live-display/public/stream` 開一條可重連 SSE 長連線。
  正常啟動先取得 latest cursor、不重播歷史，之後靠 PostgreSQL `NOTIFY` 喚醒送出 `update` frame
  （event 與已變更的 theme 一併夾帶），以 viewer-isolated FIFO 播放 collection binder；沒有合法 collection
  snapshot 的舊事件仍顯示七格循環集點卡。theme 發布後隨下一次 `update` 送達，不必重載 OBS；每筆入列時
  凍結自己的 theme，queued event 在輪到播放前會再檢查 expiry。每條串流有 15 秒 heartbeat 與 5 分鐘
  硬性 lease，到期或斷線由前端帶最後 cursor、以指數退避加 jitter 重連補齊事件，不 fallback 回週期
  polling。
- Dashboard 的 `Live Display` 頁位於 `/modules/live-display`，依「顯示內容、卡片樣式、
  預覽與測試、加入直播畫面」排序；每個 block 都提供不執行正式功能流程的測試動畫。頁面可啟停 feed、
  複製／輪替 capability URL、編輯／預覽／發布該 block 的頻道樣式；設定 mutation
  分別使用操作鎖，避免重複提交或舊 response 覆蓋新狀態。
- `/live-display#key=<uuid>&preview=1` 會從 cursor 0 讀取仍未過期事件，只供設定預覽／開發驗證。
- Vite development 另提供 `/dev/live-display` 隔離頁面預覽；production bundle 不包含此路由，
  正式 Dashboard 頁仍需登入並只存取目前租戶設定。
- `!ovltest [1-9999]` 僅在 `ENVIRONMENT=development` 且 chatter 就是該頻道 broadcaster 時生效；
  它只寫一筆 10 分鐘的 `system` preview event，不寫 `viewer_checkins`、不增加正式 count。
