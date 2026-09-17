# AI Assistant Harness

Niibot 的 AI 是有界的聊天 assistant，不是能自行規劃、使用工具或長時間執行任務的 agent。
Twitch 與 Discord 共用同一套 provider-neutral pipeline，平台層只負責收集 context、權限／冷卻與顯示。

## 分層

| 層                     | 責任                                                                       | 不負責                      |
| ---------------------- | -------------------------------------------------------------------------- | --------------------------- |
| Platform orchestration | 收集頻道設定、知識包、短期歷史、使用者輸入；映射平台訊息                   | provider SDK、fallback 細節 |
| Prompt compiler        | 驗證權威順序、標記不可信資料、套用字元預算                                 | 選模型、輸出過濾            |
| Provider adapter       | 映射 role／reasoning 參數、呼叫 SDK、正規化錯誤與 usage                    | 決定是否 fallback           |
| Bounded router         | deadline、attempt 上限、錯誤分類、circuit breaker                          | 修改 prompt、繞過安全拒答   |
| Output processor       | 移除 reasoning tag、正規化、截斷、平台前安全掃描                           | 重新呼叫模型                |
| Platform renderer      | 將 `ok`／`empty`／`blocked`／`unavailable`／`misconfigured` 轉成使用者訊息 | 解析 provider 例外字串      |

`AssistantRequest` 與 `ProviderRequest` 分離；應用程式持有所有對話狀態，不依賴任一供應商的 thread state，
因此 fallback 不會遺失當次 context。

## Prompt 權威與資料邊界

順序固定且由型別驗證：

1. `core_policy`：應用程式不可覆寫的安全與保密邊界。
2. `product_contract`：Twitch／Discord 的輸出格式、長度與平台行為。
3. `channel_persona`：頻道主可編輯的人設資料。
4. `retrieved_context`：知識包檢索結果。
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

## Twitch 短期對話記憶

第一版是 opt-in、process-local 的短期延續能力，不是頻道知識庫或觀眾側寫：

- 只收錄明確 `!ai`／`!問` 且最終 `outcome=ok` 的 user/assistant pair；一般聊天、blocked、empty、錯誤與 timeout 不保存。
- key 為 `(twitch, channel_id, Twitch user id)`，不同頻道與觀眾完全隔離；user id 只存在記憶索引，不注入 prompt、log 或 metrics。
- 每個 session 最多 2 exchanges、1000 字元，最後一次成功寫入後 10 分鐘到期。
- 全程序最多 500 sessions、500,000 內容字元；超額以 LRU 淘汰完整 session，單一超大 turn 直接拒絕保存。
- 使用單一有界 in-memory store，沒有 per-channel timer/task；讀寫時 lazy expiry，程序重啟即清空。
- Dashboard 預設 `memory_enabled=false`；設定更新、停用頻道或關閉記憶時會清除該頻道現存 session。

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
`ai_status.providers` 顯示註冊狀態，`ai_status.circuits` 顯示運行期故障狀態，`ai_status.memory` 只顯示聚合容量；
三者都不包含 secret、prompt、知識內容、viewer key 或聊天訊息。

結構化 log 只記錄 request id、outcome、provider/model、attempt/fallback 數、latency 與 provider 回傳的 token usage。

## 明確不做

目前不保存全頻道聊天、不自動萃取長期偏好、不建立觀眾 profile、不將記憶寫入 Postgres／向量資料庫，也不讓 persona
改寫 generation limits 或安全政策。日後若加入頻道知識，必須是頻道主可查看、可編輯、可刪除的 curated knowledge，
與短期對話記憶維持不同資料生命週期。
