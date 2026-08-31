# Bot Accounts、租戶協作與 Twitch MOD 同步

> 狀態：**Phase 0–2 已實作；Phase 3–6 仍為目標架構**（2026-08-31）。
> 本文件承接現行 [Admission & Tenancy Model](admission-and-tenancy.md)，定義 Bot OAuth 邀請、
> 租戶私有 Bot 帳號、per-tenant sender、Owner／MOD Dashboard 與可選 Twitch MOD 同步。

## 目前已交付的邊界

- Phase 0：`tokens.encryption_version`、Fernet envelope、bounded backfill、`identity_id ON DELETE SET NULL`，
  以及 TwitchIO 同 identity token store spike；同一 identity 的 broadcaster／Bot credential 採 scope union 契約。
- Phase 1：identity-only collaborator login、server-resolved tenant list、Owner／MOD capability、
  `TenantContext` 與 workspace selector foundation。
- Phase 2：`bot_accounts`、`channel_bot_accounts`、一次性 OAuth invite、tenant audit、Owner Settings card、
  public consent/result page、Admin Niibot reset 與 `bot_token_updated` runtime hot reload。
- 尚未交付：sender selection／unlink active guard、manual MOD invite source model、Twitch MOD sync、完整 private API
  tenant-path migration，以及 RLS enable。這些仍依 Phase 3–6 go/no-go 執行。

## 目標

1. 實況主可從 Settings 產生 Bot OAuth 邀請 URL，讓另一個 Twitch 帳號授予 `BOT_SCOPES`。
2. OAuth callback 直接安全更新後台 token，取代 `backend/scripts/twitch_oauth.py --role bot` 的本機作業。
3. 每個租戶只看得到 system-default Niibot 與自己取得授權的 Bot 帳號。
4. 每個頻道可獨立選擇 sender；A 的選擇、token 更新或失敗不得影響 C 的選擇。
5. Dashboard 人員權限維持兩級：Tenant Owner 與 MOD／編輯者。
6. Owner 可在 Settings 選擇把 Twitch MOD 同步為 Niibot MOD；功能預設關閉。
7. Bot provider、Dashboard 使用者、tenant member 與 runtime sender 必須是四個獨立概念。

## 非目標

- 第一版不做 commands-only、analytics-only 等細顆粒 permission grants。
- 第一版不提供 viewer 角色；既有 DB constraint 暫時保留 `viewer` 只為 migration 相容。
- Twitch MOD sync 第一版不做個別 deny list 或每人例外。
- Bot OAuth 不會自動建立 tenant、membership 或 Dashboard 權限。
- 不把 system owner 的 `/admin` 權限與 tenant owner 混為同一角色。

## Nightbot／Chiwabot 策略借鏡

- Nightbot 採 channel manager 模式：Owner 手動把可信任的人加入 manager，manager 登入自己的帳號後可在可管理的
  channels 間切換，且 dashboard 管理權不等同 Twitch chat MOD。這支持 Niibot 使用明確 tenant grant、獨立
  collaborator login 與 workspace selector，而不是把 Twitch MOD 身分直接視為全域 Dashboard 權限。
- Nightbot manager 的控制範圍很廣；Niibot 第一版採更保守的兩級模型：MOD 可處理營運設定，但 credential、成員、
  金流、capability key 與安全/audit 保持 Owner-only。這維持 Nightbot 的低操作成本，同時縮小 credential 外洩面。
- Twitch MOD 自動同步只作可選的 grant source，預設關閉；它補足 Nightbot 需要逐一加入 manager 的操作成本，但不
  取代手動 grant，也不把 Twitch 的聊天角色永久複製成 Niibot 身分。
- 截至本規劃日，未找到可公開核實的 Chiwabot 官方權限／帳號委派文件；因此不把未驗證的 Chiwabot 行為寫成
  security invariant。若取得其實際畫面、API 或文件，再以同一 identity／tenant／credential／runtime 四層模型比較。

參考：[Nightbot Managers](https://docs.nightbot.tv/control-panel/managers)、
[Nightbot Commands](https://docs.nightbot.tv/control-panel/commands)。

## 已確認的產品決策

| 項目            | 決策                                                                |
| --------------- | ------------------------------------------------------------------- |
| Tenant          | 一個 Twitch broadcaster channel 等於一個 tenant                     |
| Dashboard 角色  | `owner` + `manager`；UI 將 `manager` 顯示為「MOD／編輯者」          |
| Bot provider    | 只提供 credential，不因此成為 User、member 或 MOD                   |
| 自訂 Bot 可見性 | 只透過 `channel_bot_accounts` 對授權 tenant 可見                    |
| 共用例外        | Niibot 是唯一 system-default Bot，所有 tenant 都可使用且不可 unlink |
| Token reset     | 更新該 Twitch identity 的 Bot credential 並即時通知 runtime reload  |
| Twitch MOD sync | channel-scoped、Owner-only、Settings 內設定、預設關閉               |
| MOD 登入        | 必須用自己的 Twitch identity 登入；同步本身不建立 ghost User        |
| MOD 權限        | 營運設定可編輯；credential、成員、金流與安全設定不可操作            |
| 授權來源        | `manual` 與 `twitch_mod_sync` 是 grant source，不是兩種角色         |

## 剩餘缺口與已完成基礎

### Collaborator 登入基礎已完成，grant source 尚待 Phase 4–5

原本 Twitch callback 一律保存 broadcaster token、建立自己的 channel、處理 admission，最後把登入者設為
該 channel owner；`require_tenant_access` 也無條件依賴 `require_activated`。Phase 1 已加入獨立
`collaborator_login` callback、server-resolved tenant access 與 membership lock 語意，且不保存 broadcaster token
或建立自己的 tenant。

但在 Phase 4 的 manual grant 與 Phase 5 的 Twitch sync source model 完成前，仍不能正式開放未登入 MOD 的邀請：

- 不啟用時會被 `require_activated` 擋住。
- 若為了通過而把他設成 active，migration 084 會連帶啟用他自己的 channel。

已交付 callback 只證明 Twitch identity、建立／連結 User/Identity，並只在已有 effective tenant access 時建立
session；pending external identity grant 的 materialize 仍待 `channel_member_grants`。

### `channel_members` 無法保存多重來源

現行 PK 是 `(channel_id, user_id)`，無法表示：

- 同一人同時有 manual 與 Twitch sync grant。
- 移除其中一個來源但另一個仍有效。
- 尚未登入、只有 Twitch platform user ID 的 MOD。
- sync grant 的最後確認時間與失效時間。

因此 `channel_members` 只能作 effective projection，授權來源必須另表保存。

### Runtime 仍是單一 `_bot_id`

目前 chat sender、moderator API、EventSub condition、self-message suppression、mod cache、followers／chatters
查詢都使用全域 `_bot_id`。前端加 dropdown 並不能真正做到 per-tenant sender。

### RLS 尚未生效

Migration 083 只建立 policies，尚未 `ENABLE ROW LEVEL SECURITY`；而 `TenantService.bind_session()` 目前沒有
request call site，repositories 也常自行取得另一條 connection。現階段真正的隔離仍依靠 application query
中的 `channel_id`。MOD rollout 前必須先完成所有 private endpoint 的 tenant guard，RLS 另作明確 rollout。

## 身分與授權模型

```text
Twitch identity
   │
   ├── session login ──▶ User / Identity ──▶ tenant access grants ──▶ channel_members
   │                                              │
   │                                              └── owner / MOD Dashboard access
   │
   ├── broadcaster OAuth ──▶ broadcaster credential ──▶ own tenant lifecycle
   │
   └── bot OAuth invite ──▶ bot credential principal ──▶ channel_bot_accounts
                                                        │
                                                        └── runtime sender
```

核心 invariant：

- JWT 只代表登入 User，不保存 active tenant 或 role。
- 每個 private API request 都從 path 取得 `channel_id`，再即時解析 effective tenant role。
- Bot token 不代表 Dashboard session。
- Twitch MOD status 只有在 tenant 明確開啟 sync 時才成為 grant source。
- Tenant Owner 來自 `channels.owner_user_id`，不是全域 `OWNER_ID`。
- API 的 `is_owner` 應釐清為 `is_system_owner`；tenant owner 由 active tenant role 表示。

## 權限矩陣

| 功能                                  |   Tenant Owner    | MOD／編輯者 |            Bot provider             |
| ------------------------------------- | :---------------: | :---------: | :---------------------------------: |
| 查看 tenant overview／analytics       |         ✓         |      ✓      |                  —                  |
| 指令、事件、timer、trigger            |         ✓         |      ✓      |                  —                  |
| Game／Video Queue、Crosshair、AI      |         ✓         |      ✓      |                  —                  |
| Overlay theme／內容設定               |         ✓         |      ✓      |                  —                  |
| 啟停 Bot                              |         ✓         |   建議 ✓    |                  —                  |
| 從已授權且 ready 的 Bot 中切換 sender |         ✓         |   建議 ✓    |                  —                  |
| 產生 Bot OAuth invite／reauthorize    |         ✓         |      —      |            點擊授權連結             |
| Unlink Bot account                    |         ✓         |      —      | 僅能撤回其 Twitch 授權（v1 為全域） |
| 查看／輪替 Overlay capability key     |         ✓         |      —      |                  —                  |
| 成員邀請／移除、Twitch MOD sync       |         ✓         |      —      |                  —                  |
| 金流 credential                       |         ✓         |      —      |                  —                  |
| Tenant 安全與 audit                   |         ✓         |      —      |                  —                  |
| 全域 `/admin`                         | System owner only |      —      |                  —                  |

前端隱藏不是授權措施；Owner-only operation 必須有獨立 server-side dependency。

## 登入與進入流程

### Broadcaster login（保留現有用途）

用途：實況主啟用／管理自己的 channel。

1. 取得 `BROADCASTER_SCOPES`。
2. 保存 broadcaster credential。
3. `IdentityService.find_or_link()`。
4. 執行 admission entitlement／狀態機。
5. 建立或更新 own tenant + owner row。
6. 建立 JWT session。

### Collaborator login（新增）

用途：手動受邀或 Twitch sync MOD 進入別人的 tenant。

1. 使用獨立 `purpose=collaborator_login` state 與最小 identity proof。
2. 建立／連結 User、Identity；不保存 broadcaster token。
3. 依 `(platform, platform_user_id)` materialize pending grants。
4. 不建立 channel、不改 membership、不執行 admission activation。
5. 若至少有一個有效 tenant grant，建立 session 並導向該 tenant。
6. 若沒有 grant，顯示無可存取工作區，不把登入者誤導到 broadcaster activation。

Admission 規則：

- 無 membership row 的 collaborator 可以依有效 tenant grant 進入。
- `pending` 仍可作 collaborator，但不能啟用自己的 channel。
- 已存在且為 `suspended`／`rejected` 的 membership 視為全域鎖定，不得藉 collaborator grant 繞過。
- Tenant owner 的 membership 必須 active；owner 被停權或 tenant suspended 時，所有 MOD 一併拒絕進入。

### Bot authorization（新增，永不建立 session）

1. Owner 建立 30 分鐘、一次性的 invite。
2. Public consent page 只顯示 tenant 名稱、Bot scopes、期限與同意／拒絕。
3. Twitch callback 驗證 HMAC state、DB nonce hash、expiry、purpose、未消耗與 optional expected account。
4. 交換 code、驗證實際 Twitch identity 與完整 `BOT_SCOPES`。
5. 同一 transaction 完成 credential、bot account、tenant mapping、invite consume、audit。
6. 導向獨立完成頁；不建立 Niibot Dashboard session、不在 URL 或 response 暴露 token。

## 目標資料模型

實際 migration number 必須在實作當下依 repository head 配發，不在本文件預占號碼。

### `bot_accounts`

| 欄位                         | 說明                                            |
| ---------------------------- | ----------------------------------------------- |
| `platform_user_id`           | Twitch stable user ID，credential principal key |
| `platform`                   | 第一版固定 `twitch`                             |
| `identity_id`                | nullable，登入後才回連；`ON DELETE SET NULL`    |
| `login/display_name/avatar`  | 安全的 identity snapshot                        |
| `is_system_default`          | 只有 Niibot 為 true；DB 保證最多一筆            |
| `last_validated_at`          | 最近成功驗證 token/scopes                       |
| `requires_reauth/revoked_at` | credential lifecycle，不保存 tenant role        |

Token 真相仍由 credential repository 管理，不在 `bot_accounts` 複製 access／refresh token。

### `channel_bot_accounts`

- Composite PK：`(channel_id, bot_user_id)`。
- 只保存 custom Bot 的 tenant grant、creator 與時間。
- 租戶查詢必須先由此表進入，不能先取 global bot list 再前端過濾。
- System-default Niibot 由 `bot_accounts.is_system_default` 明確合成到每個 tenant response，不複製 mapping rows。
- Owner unlink 只刪本 tenant mapping；其他 tenant 的 mapping 與 credential 不受影響。

### `bot_oauth_invites`

- `purpose = link_new | reauthorize | system_default_reset`。
- DB 只保存 public token／nonce 的 hash。
- 保存 channel、creator、optional `expected_bot_user_id`、expires／consumed／declined timestamps。
- `link_new` 才能接受任意 callback identity；其餘 purpose 必須等於 expected account。
- 同 tenant 限制未完成 invite 數，callback 以 row lock 防 replay／race。

### `channel_bot_settings`

單一 `selected_bot_user_id` 無法表達 runtime rollback，改採：

| 欄位                    | 說明                                             |
| ----------------------- | ------------------------------------------------ |
| `desired_bot_user_id`   | 使用者要求的 Bot；NULL = system default          |
| `active_bot_user_id`    | runtime 已成功啟用的 Bot；NULL = system default  |
| `selection_version`     | 每次 request 單調增加                            |
| `status`                | `active \| switching \| failed`                  |
| `last_error_code`       | 安全、可顯示的錯誤 code，不保存 token／上游 body |
| `updated_by/updated_at` | audit 與 UI 狀態                                 |

### `channel_member_grants`

授權來源的 source of truth：

- `channel_id`
- `platform` + `platform_user_id`
- nullable `identity_id`／`user_id`
- `source = manual | twitch_mod_sync`
- `granted_by`
- `last_confirmed_at`
- nullable `valid_until`
- Unique `(channel_id, platform, platform_user_id, source)`

`channel_members` 保留作登入後的 effective projection：任一有效 MOD grant 存在即為 manager；所有 MOD grants
消失才移除 manager row。Owner row不走 grant table，也不能被 reconcile 刪除。

### `channel_collaboration_settings`

- `sync_twitch_mods BOOLEAN NOT NULL DEFAULT FALSE`
- `last_sync_started_at`／`last_sync_succeeded_at`
- `sync_status = disabled | healthy | unhealthy`
- `last_error_code`

### Audit

建立 append-only tenant audit，至少記錄：

- authenticated actor User
- external Twitch actor／provider identity（若有）
- beneficiary channel
- target type／ID
- invite、grant、revoke、sync、selection、fallback、credential update event
- redacted metadata

Audit、error、URL、PG NOTIFY payload 永遠不包含 access／refresh token 或 OAuth code。

### 既有 schema 修正

- `tokens.identity_id` 目前是 `ON DELETE CASCADE`；Bot credential 可獨立於 User 存在，需改為
  `ON DELETE SET NULL`。
- `viewer` 暫留 constraint 但新 API 不建立；確認 production 無 rows 後另行移除。
- 新增外部 Bot token 前，先把 `tokens.token/refresh` 遷移為 versioned application encryption；API 與 Twitch
  runtime 共用專用 `TWITCH_TOKEN_ENCRYPTION_KEY`，禁止模糊的 decrypt-or-plaintext fallback。

## 目標 API Contract

所有 tenant private endpoint 使用 `{channel_id}` path；request body 不接受另一份 tenant ID。

### Tenant/session

- `GET /api/tenants`：登入者可存取的 tenants、role、capabilities、sync／runtime summary。
- `GET /api/tenants/{channel_id}`：有效 member。
- `GET /api/auth/twitch/collaborator/oauth`：產生 identity-only OAuth URL。
- `GET /api/auth/twitch/collaborator/callback`：materialize grants + session。

### Bot accounts

- `GET /api/tenants/{channel_id}/bot-accounts`：Owner/MOD；只回安全 summary。
- `POST /api/tenants/{channel_id}/bot-accounts/invites`：Owner-only，201。
- `GET /api/tenants/{channel_id}/bot-accounts/invites/{id}`：Owner-only status polling。
- `GET /api/public/bot-invites/{public_token}`：public safe consent summary。
- `GET /api/auth/twitch/bot/callback`：public OAuth callback。
- `DELETE /api/tenants/{channel_id}/bot-accounts/{bot_id}`：Owner-only；active／desired 時回 409。
- `PUT /api/tenants/{channel_id}/bot-account-selection`：Owner/MOD，寫 desired + version。

### Collaboration

- `GET /api/tenants/{channel_id}/members`：Owner-only。
- `POST /api/tenants/{channel_id}/member-invites`：Owner-only，建立單一 MOD invite。
- `DELETE /api/tenants/{channel_id}/members/{user_id}`：Owner-only，移除 manual source。
- `GET/PATCH /api/tenants/{channel_id}/collaboration-settings`：Owner-only。
- `POST /api/tenants/{channel_id}/twitch-mod-sync/reconcile`：Owner-only manual reconcile。

### Authorization／錯誤邊界

- 未登入：401。
- 已登入但不是 tenant member：對 tenant resource 回 404，避免 channel ID enumeration。
- member 角色不足：403。
- invite／selection state conflict：409。
- Twitch 暫時錯誤：502／503；不得把 partial／empty response 當成功。
- Public invite lookup、callback、invite creation、selection、member mutation、sync toggle 都需要 rate limit。

## Twitch MOD 同步

### Scope 策略

- Get Moderators 可使用 `moderation:read`，也可使用現有 `channel:manage:moderators`。
- Niibot 現行 broadcaster base scopes 已有 `channel:manage:moderators`，因此完整 reconcile 通常不需追加 scope。
- `channel.moderator.add/remove` EventSub 需要 `moderation:read`；它只能作可選的即時加速，不能成為唯一真相。
- 不為預設關閉的功能強迫所有 tenant 追加 `moderation:read`。

### 固定同步語意

1. 預設關閉，只能由 tenant owner 開啟。
2. 開啟前明示「所有 Twitch MOD 都會取得 Niibot 編輯權」。
3. 開啟 transaction 必須先成功取得完整 moderator set；失敗則保持 disabled。
4. 啟用後每 15 分鐘完整 reconcile；多 API replicas 使用 advisory lock 或 `SKIP LOCKED`。
5. 成功集合新增／更新 `twitch_mod_sync` grants，撤除已不在集合中的 sync grants。
6. 每筆 sync grant 建議 `valid_until = last_confirmed_at + 1 hour`。
7. API／網路錯誤保留資料至 `valid_until`，但不得套用空集合或 partial pages。
8. Token 明確無效或兩種可讀 scope 都缺少時，立即 unhealthy，sync-only access fail closed。
9. 關閉設定立即移除全部 `twitch_mod_sync` source 並重新計算 effective members。
10. Manual grants、owner、其他 tenant grants 永遠不受同步刪除。
11. System-default Niibot ID 永遠排除。
12. 每個 private request 都即時檢查 grant expiry；撤權不依賴 JWT 到期。

現有 `fetch_all_moderators()` 在錯誤時回 `[]`，必須改成 typed complete result／exception；任一 pagination page
失敗即整次 reconcile 失敗。

## Per-tenant sender runtime

### 切換流程

1. API 驗證候選 Bot 屬於本 tenant、token 有完整 scopes、未 revoked、是該 channel 的 Twitch MOD。
2. 寫 `desired + version + switching` 並發送不含 secret 的通知。
3. Runtime 取得 per-channel lock，載入指定 credential、執行 preflight。
4. 建立新的 bot-bound subscriptions，確認必要項目全部成功。
5. 成功才寫 `active + status=active`；前端以 ack version 判斷完成。
6. 失敗保留舊 active，寫 `failed + safe error code`。
7. Restart 依 active 恢復，並重試未完成 desired；絕不直接採用 failed desired。

### EventSub 拆分

現有 catalog 混合兩類 subscription，必須拆成：

- Stable broadcaster-bound：stream、sub、bits、raid、redemption、moderator／VIP 等。
- Bot-bound：chat message、chat notification、follow moderator 等帶 sender／moderator user ID 的項目。

切換只重建 bot-bound subscriptions。短暫新舊重疊期間以 Twitch message/event ID 做 TTL dedup；必要 chat
subscription 失敗時整個切換失敗，不能因其他 subscription 成功就標示 active。

### Resolver 影響

建立 channel-scoped `BotAccountResolver`／`BotExecutionContext`，取代下列用途的 global `_bot_id`：

- `send_message(sender=...)`
- moderator／chatter／follower API 的 `moderator_id`
- ban、announcement、shoutout 等 moderation actions
- EventSub `user_id`／`moderator_user_id`
- mod status cache
- self-message loop suppression（切換期間同時忽略新舊 sender）
- welcome／reauth messages
- follower／subscriber／emote 查詢

### TwitchIO 前置 spike

同一 Twitch user ID 可能同時有 broadcaster 與 Bot token。DB 可保存兩列不代表 TwitchIO runtime 能同時選對
兩種 token。Phase 0 spike 已確認 TwitchIO token store 以 user ID 為 credential key，因此同 identity 走
union-scope 契約；Phase 3 sender selection 必須在寫入 desired selection 前強制驗證 union scopes，不能靜默覆寫。

## Frontend

### Tenant context

現有 `AuthContext.channels` 是全站 monitored channels，`NavChannels` 只是外連 Twitch，不是 workspace selector。

新增 `TenantContext`：

- accessible tenants
- active tenant + role + capabilities
- tenant switch
- access-revoked refresh／fallback

建議 private UI 改為 `/dashboard/{channel_id}/...`；舊 `/commands`、`/events` 等路徑只負責 redirect 至最近可用
tenant，避免多 tab／bookmark 依賴同一份 local storage active state。

### Settings

`/settings` 依 active tenant role 分區：

- Bot 帳號：Owner 可 invite／reauthorize／unlink；MOD 只看狀態並切換已核准 sender。
- 協作權限：Owner-only；手動 MOD 與預設關閉的 Twitch MOD sync。
- 金流：Owner-only。
- 一般營運設定：Owner/MOD。

Owner-only card 未載入資料前不得先呼叫對應 API；後端仍需完整 guard。

### 撤權 UX

任一 tenant API 回 `TENANT.ACCESS_DENIED`／等價 404 時：

1. 清除該 tenant cache。
2. 重新載入 accessible tenant list。
3. 有其他 tenant 則切換；沒有則顯示「目前沒有可管理的頻道」。
4. 不必強制登出 identity session，因使用者可能仍有 Bot provider portal 或其他 tenant。

## 資料安全

- Access／refresh token 使用 versioned application encryption；key 只存在 API／Twitch runtime secret env。
- API response、frontend state、audit、logs、errors、redirect URL 與 PG NOTIFY 不出現 token／OAuth code。
- OAuth invite token 與 nonce 只存 hash；state 有 HMAC、purpose、expiry 與 DB one-time consume。
- Callback transaction 使用同一 DB connection；repositories 必須支援 `conn=` 或由專用 service 集中 SQL。
- Tenant list與 bot list由 server query boundary隔離，不依賴前端 filtering。
- Owner unlink A 不得刪除 C 的 mapping；只有零 mapping 的非預設帳號才清除本地 credential。
- Bot provider v1 從 Twitch Connections 撤權會使該 credential 對所有 tenant 失效；各 mapping 保留為
  `requires_reauth`，runtime 逐 tenant fallback 並 audit。Tenant-specific provider portal 列為後續版本。
- Owner 主動 unlink active／desired Bot 回 409，要求先切回 Niibot；token involuntary invalid 時 runtime 自動
  fallback Niibot 並 audit。
- New RLS policies涵蓋 grant、mapping、settings、audit；啟用前需證明 API transaction 正確 bind GUC。
- API DB role與 Twitch background role分離；background role才可 BYPASSRLS。

## 影響範圍

### Backend API／shared

- OAuth／identity／admission：`auth_router.py`、`oauth_service.py`、`identity_service.py`、`admission_service.py`。
- Tenant access：`core/dependencies.py`、`tenant_service.py`、`channel_member.py`。
- Credential：`channel.py` repository、token models、crypto、config／env manifests。
- 新增 BotAuthorization、BotAccount、Collaboration、TenantSession services／repositories／models。
- Private routers：AI、analytics、channels、commands、crosshairs、events、game queue、matcher、triggers、stats、
  timers、video queue、community overlay、payment config。
- OpenAPI 與 typed error catalog。

### Twitch runtime

- `core/bot.py`
- `core/subscription_manager.py`
- `core/eventsub_catalog.py`
- `core/session_service.py`
- `core/_notify_mixin.py`、`core/_message_router_mixin.py`
- `components/events.py`、`channel_points.py`、`timer_manager.py`、`viewer_stats.py`、`ai.py`、`games.py`、
  `general_commands.py`，以及所有 global `bot_id`／`sender=` call sites。

### Frontend impact

- `AuthContext`、`ProtectedRoute`、`App` routes。
- 新 `TenantContext` 與 workspace switcher；不可復用 platform `BotSwitcher`。
- `Settings` 分區與 Bot consent／result public pages。
- `api/config.ts`、cache keys 與所有 tenant-scoped API modules。
- Admin `BotStatusPanel` 的 system-default reset flow。

### Operations／documentation

- 新 token encryption secret、API/Bot env contract、migration/backfill runbook。
- Runtime status／metrics：active senders、failed selections、sync health、stale grants、credential reauth。
- 架構總覽、admission/tenancy、API reference、部署與 troubleshooting 文件。

## 實作順序與 go/no-go

### Phase 0 — Contract、加密與風險 spike

- 鎖定 schema/API/error contracts與失敗測試。
- 導入 Twitch token versioned encryption、修正 identity FK `SET NULL`。
- 驗證 TwitchIO 同一 user ID 的 bot+broadcaster token 行為。
- **Go/no-go：** spike 必須得出明確 token selection 策略。

### Phase 1 — Tenant session foundation

- `collaborator_login` purpose。
- Tenant list、Owner/MOD dependencies、membership lock語意。
- Frontend TenantContext／workspace routes。
- 先遷移 owner-sensitive Settings endpoints，再逐 router遷移。
- **Go/no-go：** cross-tenant tests證明 A 的 MOD不能讀 C。

### Phase 2 — Bot credential registry／OAuth invite

- Bot accounts、tenant mapping、invite、audit migrations。
- Owner Settings Bot Card與 public consent/result page。
- Admin system-default Niibot reset，正式取代 local script。
- Runtime hot reload credential，但此階段所有 tenant仍使用 Niibot。
- **Go/no-go：** callback原子性、replay防護、token加密與名單隔離通過。

實作結果：migration 100–102、owner/public/admin API、callback transaction、Settings/public UI 與 system Bot hot reload
已完成；本機 PostgreSQL migration smoke、完整 backend/frontend suites、lint、typecheck 與 production build 均已驗證，
細節記錄於 `tasks/todo.md` Review。
真正 per-tenant sender 尚未啟用，因此自訂 credential 在 Phase 2 只登錄，不會進入全域 TwitchIO token store。

### Phase 3 — Per-tenant sender

- Desired/active/version runtime contract。
- Resolver／CredentialBroker、EventSub拆分、per-channel lock、dedup、ack／restart reconcile。
- 遷移所有 send/mod API call sites。
- **Go/no-go：** 切換失敗保留舊 active；A 切換不影響 C。

### Phase 4 — Manual MOD Dashboard

- Grant source model、manual invite/list/remove。
- 完整 Owner/MOD capability矩陣與 Settings分區。
- 所有 private APIs完成 `{channel_id}` tenant guard。
- **Go/no-go：** revoke後下一個 request立即失效，Owner-only secrets無法被 MOD讀取。

### Phase 5 — Optional Twitch MOD sync

- Typed moderator fetch、scheduler lock、完整 reconcile、expiry、fail-closed。
- Settings toggle、health、last success、manual sync。
- EventSub只作有 scope時的加速。
- **Go/no-go：** empty vs failure、manual+sync union、disable/revoke、stale與system bot exclusion全數通過。

### Phase 6 — RLS與漸進 rollout

- API transaction綁定 tenant GUC，補新 tables policies。
- API與Bot使用不同 DB roles；staging逐表 enable。
- Feature flags依序開 Bot invite、sender selection、manual MOD、Twitch sync。
- 觀察 metrics、執行 rollback drill，再production rollout。

## 驗證矩陣

- OAuth：expiry、tamper、replay、wrong purpose、wrong expected account、decline、concurrent callback。
- Identity：Bot callback不建 User；collaborator callback不建 channel/token/membership。
- Credential：DB ciphertext、refresh、key rotation、invalid token、scope diff、零 mapping清除。
- Tenant：A/C mapping隔離、ID enumeration、Owner/MOD矩陣、membership locked、tenant suspended。
- Runtime：hot reload、failed desired、restart、old/new event dedup、same-user dual token、automatic fallback。
- Collaboration：manual + sync union、未登入 pending identity、login materialize、跨 tenant revoke。
- Sync：authoritative empty、partial page failure、API outage、scope revoke、15 分鐘 reconcile、1 小時 expiry。
- Secrets：payment、Bot credential、Overlay key只限 Owner；logs／audit／notify皆redacted。
- Frontend：desktop／390px、role-based Settings、tenant switch、多 tab／bookmark、access revoked fallback。
- Verification：focused + full backend/frontend suites、coverage、Ruff、mypy、ESLint、TypeScript、build、migration smoke、
  Docker runtime smoke與實際 OAuth staging journey。

## 待確認細項（建議預設）

| #   | 細項                              | 建議預設                                                              |
| --- | --------------------------------- | --------------------------------------------------------------------- |
| D1  | MOD 是否可啟停 Bot                | 可以；視為營運操作                                                    |
| D2  | MOD 是否可切換已核准 sender       | 可以；不能 invite、reauthorize、unlink                                |
| D3  | Private Dashboard URL             | `/dashboard/{channel_id}/...`，舊路由redirect                         |
| D4  | Manual MOD invite期限             | 7 天、一次性、Owner可撤銷                                             |
| D5  | Bot OAuth invite期限              | 30 分鐘、一次性；同 tenant最多5筆pending                              |
| D6  | Twitch MOD reconcile              | 每15分鐘；grant有效1小時；明確scope/token失效立即fail closed          |
| D7  | 個別 Twitch MOD例外               | v1不提供deny list；需要例外就關閉sync並用manual invite                |
| D8  | 主動unlink active Bot             | 回409，要求先切回Niibot；非預期失效才自動fallback                     |
| D9  | Bot provider自助撤回              | v1先用Twitch Connections全域撤權；tenant-specific portal列後續        |
| D10 | 同一identity同時是broadcaster+Bot | Phase 0 spike後決定 CredentialBroker或union-scope，不允許未驗證地上線 |
| D11 | DB role字串                       | 內部暫留 `manager`，UI統一顯示「MOD／編輯者」                         |
| D12 | RLS                               | MOD production rollout前必須完成staging逐表enable與rollback drill     |

## Twitch 官方依據

- [Get Moderators](https://dev.twitch.tv/docs/api/reference/#get-moderators)：可用
  `moderation:read`，已有 moderator management需求時也可用 `channel:manage:moderators`。
- [EventSub subscription types](https://dev.twitch.tv/docs/eventsub/eventsub-subscription-types/)：
  `channel.moderator.add/remove` 需要 `moderation:read`。
- [OAuth scopes](https://dev.twitch.tv/docs/authentication/scopes/)：OAuth只應要求功能需要的 scopes。
