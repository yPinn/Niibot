# AI Assistant Harness

Niibot 的 AI 是有界的聊天 assistant，不是能自行規劃、使用工具或長時間執行任務的 agent。
Twitch 與 Discord 共用同一套 provider-neutral pipeline，平台層只負責收集 context、權限／冷卻與顯示。

## 分層

| 層                     | 責任                                                                            | 不負責                      |
| ---------------------- | ------------------------------------------------------------------------------- | --------------------------- |
| Platform orchestration | 收集頻道設定、知識包、短期歷史、使用者輸入；映射平台訊息                        | provider SDK、fallback 細節 |
| Prompt compiler        | 驗證權威順序、標記不可信資料、套用字元預算                                      | 選模型、輸出過濾            |
| Provider admission     | 預估 token、provider/model 共用 RPM／TPM／RPD、頻道公平排隊與 overload shedding | 修改 prompt、等待無上限     |
| Provider adapter       | 映射 role／reasoning 參數、呼叫 SDK、正規化錯誤與 usage                         | 決定是否 fallback           |
| Bounded router         | deadline、attempt 上限、錯誤分類、circuit breaker                               | 修改 prompt、繞過安全拒答   |
| Output processor       | 移除 reasoning tag、正規化、截斷、平台前安全掃描                                | 重新呼叫模型                |
| Platform renderer      | 將 `ok`／`empty`／`blocked`／`unavailable`／`misconfigured` 轉成使用者訊息      | 解析 provider 例外字串      |

`AssistantRequest` 與 `ProviderRequest` 分離；應用程式持有所有對話狀態，不依賴任一供應商的 thread state，
因此 fallback 不會遺失當次 context。

## Prompt 權威與資料邊界

順序固定且由型別驗證：

1. `core_policy`：應用程式不可覆寫的安全與保密邊界。
2. `product_contract`：Twitch／Discord 的輸出格式、長度與平台行為。
3. `channel_persona`：頻道主可編輯的人設，或已發布 Role-play revision 的演繹摘要；兩者互斥。
4. `retrieved_context`：角色 Lore、頻道知識包或 Twitch emote 等已檢索資料。
5. `conversation_history`：選擇性、短效且不可信的對話歷史。
6. `user_input`：本次使用者輸入，且必須恰好一份。

前兩層編譯成穩定的 developer/system 前綴；其餘內容放進標記為 `CONTEXT_DATA` 的 JSON user message，
current user input 再以獨立 JSON message 傳遞。persona、知識與歷史即使含有「忽略規則」文字，也只被視為資料。

字元預算先限制各動態區段，再依 history → context → persona → user 的順序縮減；core policy 與 product contract
不會被靜默截斷。若固定前綴本身超出總預算，直接回報設定錯誤。

## Persona v2

頻道設定不再把所有內容塞進一段自由文字，而是映射為明確責任：

| 分組        | 欄位                                                          | Prompt 位置        |
| ----------- | ------------------------------------------------------------- | ------------------ |
| Identity    | `bot_name`、`self_pronoun`                                    | `channel_persona`  |
| Voice       | `tone_preset`、既有 `persona` 進階補充                        | `channel_persona`  |
| Signature   | `catchphrase`、`catchphrase_frequency`                        | `channel_persona`  |
| Examples    | 最多 3 則、每則最多 120 字的 assistant-only `example_replies` | `channel_persona`  |
| Output rule | `response_lang`、`refusal_style`                              | `product_contract` |
| Runtime     | `max_tokens`、`enabled`、`cooldown`、`min_role`               | 不進 persona       |

`tone_preset` 與口頭禪頻率由固定 enum 對應程式內 guidance；未知值一律回退保守預設，不能把任意文字提升為高權威指令。
所有頻道可編輯文字仍序列化為 `CONTEXT_DATA`。既有 `persona` 欄位保留，因此 migration 不會破壞已儲存的人設。
`audience_reference` 暫留在 DB/API 作向後相容，但不再注入 prompt 或顯示於設定頁；實測顯示免費模型會把裸露的群體稱呼
當成每則必用的台詞，與 `!ai` 的單一提問者互動不符。

### Persona 自然度契約

Twitch 的單則回覆只有 100 字，因此預設採低強度角色表現：答案本身優先，角色只作修飾。每則回覆至多使用一種明顯
角色標記，例如特殊自稱、觀眾稱呼、口頭禪或 emote；這些欄位都是可選偏好，不要求每則出現。示例只描述語氣與節奏，
不得當成固定台詞、事實或回答模板。

### Factory defaults 與角色範本邊界

新頻道與使用者主動執行「重設預設值」時採用保守設定：`catchphrase_frequency=off`、
`refusal_style=polite`、`cooldown=30`。這可降低免費模型過度重複口頭禪、把婉拒誤演成系統故障，以及短時間內大量請求的風險。

角色範本只覆蓋 identity／voice／signature／examples，不修改婉拒方式、短期記憶、啟用狀態、冷卻時間或最低使用身份。
Migration `123_ai_settings_default_preferences.sql` 只變更資料庫未來的 column defaults，不回填既有資料；已儲存的頻道選擇保持不變。

Prompt JSON 將自稱寫成帶條件的 `self_reference_when_needed`，而非看似每則必用的裸欄位。對全體聊天室喊話是另一種
互動意圖，不應把群體稱呼放進每個單一提問者的 prompt。

內建 preset 不預載口頭禪，避免無狀態模型把 `rare` 誤解成「這次就使用」。自訂口頭禪仍可使用，但頻率 enum 是模型的
語氣提示，不是精準機率或跨請求計數器；需要嚴格比例或禁止連續出現時，應在應用層加入有界 cadence state。
內建 preset 也統一使用自然的「我」；強自稱仍可自訂，但不作為辨識角色的主要手段。

自然度回歸以四類合成情境評估：知識問答、錯誤更正、日常閒聊，以及要求攻擊他人的拒答情境。成功輸出必須同時符合：

- 先回答或處理當前意圖，角色語氣不延遲答案。
- 不連續重複自稱、受眾稱呼、口頭禪或相同示例句。
- 機智不變成人身攻擊，傲嬌不變成冷落，元氣不讓每句都成為感嘆句，沉穩不強塞人生感悟。
- 維持 100 字、1–2 句、單段與既有安全政策。

目前不另增 `style_intensity` 欄位：固定的低強度契約加上 `tone_preset`／自由文字已能覆蓋 Twitch 的短回覆需求。
只有實際輸出評估顯示多數頻道需要在同一 persona 間穩定切換強弱，才加入有界 enum，而非再增加自由文字層。

## Twitch Canon Role-play runtime

Role-play 與 Persona 共用同一組固定 safety、Twitch product contract、provider router、deadline 與 output processor，
但各自使用明確的 mode contract。Persona 的風格提示可以低強度使用；Role-play 的身分、聲線、知識視角與互動方式
是必須持續維持的演出契約，不是可選裝飾。Role-play 每次讀 active immutable revision 的 compact capsule、依目前問題
解析最多一條且合計不超過 600 字的可知 Lore、同 revision 短期歷史、頻道啟用的共用知識包／emote 與 user input；
不載入 Persona 自由文字。

Lore 與知識包有不同來源語意：`roleplay_lore` 是角色在目前故事進度可知的內容；`knowledge_pack` 是通訊介面提供的
外部參考。模型可以用角色聲線解釋知識包，但不能把它改寫成角色親身經歷或作品 Canon。Twitch 每次最多注入兩條完整
知識內容、合計 2,000 字，不在 JSON 中間做字串截斷；ASCII 關鍵字以 ASCII alphanumeric 邊界匹配，因此
`誰是Roger` 可命中 `Roger`，`progername` 不會誤命中。
pointer 缺漏、revision 不屬於該頻道、compiled artifact 驗證失敗或 pointer／revision 不一致時 fail closed，且不呼叫模型。

成功生成後，Twitch 會繞過 cache 直接重讀目前 assistant scope。若生成期間 mode 或 revision 已變更，舊輸出不送出、
不寫入記憶，只提示觀眾重新提問；Bot sender 則維持 send-time resolver，角色與 OAuth 帳號互不成為彼此的 owner。

## Twitch 短期對話記憶

第一版是 opt-in、process-local 的短期延續能力，不是頻道知識庫或觀眾側寫：

- 只收錄明確 `!ai`／`!問` 且最終 `outcome=ok` 的 user/assistant pair；一般聊天、blocked、empty、錯誤與 timeout 不保存。
- key 為 `(twitch, channel_id, Twitch user id, assistant scope)`；Persona scope 固定為 `persona`，Role-play scope 為
  `roleplay:<revision_id>`，不含 Bot sender。不同頻道、觀眾與角色 revision 完全隔離；user id 只存在記憶索引，
  不注入 prompt、log 或 metrics。
- 每個 session 最多 2 exchanges、1000 字元，最後一次成功寫入後 10 分鐘到期。
- 全程序最多 500 sessions、500,000 內容字元；超額以 LRU 淘汰完整 session，單一超大 turn 直接拒絕保存。
- 使用單一有界 in-memory store，沒有 per-channel timer/task；讀寫時 lazy expiry，程序重啟即清空。
- Dashboard 預設 `memory_enabled=false`；停用頻道、重設 AI 設定或明確關閉記憶會立即清除該頻道 session。
  一般設定 refresh 只失效 cache，不因修改名稱、冷卻或輸出偏好而清除對話；assistant scope 事件只淘汰其他 scope，
  因此重複的同 scope 事件不會誤清目前 session。

歷史以 `source=ephemeral_conversation` 的 JSON 放入不可信 `conversation_history`，不包含 viewer 名稱或 ID。
健康度只輸出 active sessions、內容字元數與 eviction/rejection counters，永不輸出 key 或對話內容。

只有在需要多個 Twitch bot replicas 共享歷史、要求程序重啟後仍延續，或長期接近 500 active sessions 並持續發生
LRU/budget eviction 時，才值得評估 Redis；在此之前 Postgres/向量資料庫只會增加留存與刪除風險。

## 免費模型路由

| 平台    | 固定順序                                                                                                 | 總 deadline | 單次上限 | attempts |
| ------- | -------------------------------------------------------------------------------------------------------- | ----------: | -------: | -------: |
| Twitch  | Groq `openai/gpt-oss-120b` → OpenRouter `inclusionai/ling-3.0-flash-vl:free`                             |          8s |       4s |        2 |
| Discord | Groq `openai/gpt-oss-120b` → Gemini `gemini-3.5-flash` → OpenRouter `inclusionai/ling-3.0-flash-vl:free` |         40s |      15s |        3 |

Discord 仍把 Gemini 保留為不同供應商／模型族的品質備援，但不放第一順位：qualification 中 Groq 為 21/21，
Gemini 為 20/21（一次 429），且 Gemini 成功延遲約 5–13 秒。

OpenRouter 只使用明確設定的固定模型，request 帶零價格上限；`free_models.json` 不會在 production 動態輪詢，
避免免費名單變動時意外選到未知品質或付費模型。

### 共用免費額度 admission

模型呼叫前會從已編譯 request 預估 input token，並加上 `max_output_tokens` 作保守 reservation；成功後再以 provider
回傳的實際 usage 修正 token 數。RPM／TPM／RPD 以 `(provider, model)` 分開計算，所以 Groq 額度不足不會誤傷
Gemini 或 OpenRouter。等待者以不含 prompt／viewer 的 platform + channel scope 輪轉；單一頻道無法靠大量並發插隊。

目前配置保留安全餘裕，且把同一組 key 的容量靜態分配給兩個單 process runtime：

| Runtime | Groq local envelope                | Gemini local envelope | OpenRouter local envelope |
| ------- | ---------------------------------- | --------------------- | ------------------------- |
| Twitch  | 22 RPM／6,000 TPM／780 rolling RPD | —                     | 13 RPM／750 rolling RPD   |
| Discord | 5 RPM／1,700 TPM／120 rolling RPD  | 4 RPM                 | 4 RPM／150 rolling RPD    |

queue 有固定上限，Twitch 最多等 150ms、Discord 最多等 500ms；容量仍不足就把該 provider 視為本地 429，直接走既有
fallback。這不會開啟 provider circuit，因為不是外部服務故障；真正的 429 仍依 `retry-after` 與 circuit 規則處理。
本地 admission 不在 request path 睡到下一個一分鐘窗口，也不縮短單次回答的 token 上限。

這一版的 deployment mode 明確標記為 `partitioned-local`：只適用單一 Twitch process + 單一 Discord process，兩者以
靜態 allocation 避免合計超額。production Compose 以固定 `container_name` 保持兩個 runtime 各一份，contract test 也會在
加入 `replicas:` 時失敗。健康度的 `capacity_guard` 固定輸出 `max_replicas=1`、`distributed=false` 與
`shared_provider_accounts=true`，避免 operator 把 local counters 誤判為跨程序協調。

若未來任一 runtime 水平擴展成多 replica，這是 architecture gate：部署前必須先改為 PostgreSQL／Redis distributed
reservation，不能讓每個 replica 各自複製同一份額度。prod／staging 若共用 provider account，應優先拆成不同 provider
project/key 並設定 provider-side cap；單一環境的資料庫 limiter 無法協調另一個隔離資料庫。程序重啟也會重置本地 rolling
counters，因此 RPD 是降低意外耗盡風險的保守閘門，不是 provider 帳務的 durable 精準計量；真正餘額與限額仍以
provider console／response headers 為準。

## Fallback 與 circuit breaker

| 結果                                       | fallback                          | circuit 行為                                |
| ------------------------------------------ | --------------------------------- | ------------------------------------------- |
| timeout、429、網路、5xx、model unavailable | 是（仍受 deadline／attempt 限制） | 累積暫時失敗，達門檻後 open                 |
| 401／403                                   | 否                                | provider 標為 unhealthy，程序生命週期內跳過 |
| 400／驗證錯誤                              | 否                                | 視為 misconfigured                          |
| safety refusal                             | 否                                | 視為正常 blocked，不用另一模型繞過          |
| 空回覆                                     | 否                                | 回傳 empty                                  |
| 成功                                       | 結束                              | 清除失敗並關閉 circuit                      |

open circuit 冷卻後只允許一個 half-open probe。所有第三方例外在 adapter 邊界轉成不含 raw body、prompt 或 key 的
`ProviderFailure`。

## 設定與健康度

每個啟用的 provider 必須同時設定 API key 與 model；不提供程式內 model default：

- 兩者皆空：`disabled`
- 只有其一：`misconfigured`，並標示 `missing_key` 或 `missing_model`
- 兩者皆有：`ready`

bot `/status` 的 `ai_model` 與 `ai_status` 直接取自已載入的 harness registry，而非重新推測環境變數。
`ai_status.providers` 顯示註冊狀態，`ai_status.circuits` 顯示運行期故障狀態，`ai_status.capacity` 顯示各
provider/model 的 minute requests／tokens、rolling daily requests、queue depth 與上限，`ai_status.capacity_guard`
顯示目前只允許單 replica 的部署契約，`ai_status.memory` 只顯示聚合容量；全部都不包含 secret、prompt、知識內容、
viewer key 或聊天訊息。

結構化 log 只記錄 request id、outcome、provider/model、attempt/fallback 數、latency 與 provider 回傳的 token usage。

## 明確不做

目前不保存全頻道聊天、不自動萃取長期偏好、不建立觀眾 profile、不將記憶寫入 Postgres／向量資料庫，也不讓 persona
改寫 generation limits 或安全政策。日後若加入頻道知識，必須是頻道主可查看、可編輯、可刪除的 curated knowledge，
與短期對話記憶維持不同資料生命週期。
