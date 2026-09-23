# Role-play 角色系統 V1 規劃

## 文件狀態

本文件記錄產品與架構決策。Phase 1 共用 domain、validator、deterministic
compiler、Lore resolver 與 prompt adapter 已完成；Phase 2 的 A/B/C runner、
輕量 runtime profile 與 Groq gate 已完成。Phase 3A 已新增 tenant-owned draft、
immutable published revision 與 Persona／Role-play active pointer；Phase 3B 已新增
provider/model 共用容量與頻道公平 admission；Phase 3C 已新增 tenant-path authoring
API、strict mutation boundary 與 versioned assistant-scope notification；Phase 3D 已接上
Twitch compact runtime、revision-scoped memory 與 in-flight scope recheck。
Phase 4 已接上 tenant-aware AI 設定頁、Persona／Role-play 模式框架、角色清單與七步非技術 Dashboard wizard。
Phase 5 已完成已發布角色的私人檔案匯出／匯入、相同版本重用與非技術確認流程；公開連結、市集與獨立世界包仍不在
V1 範圍。

## 核心決策

- Persona Assistant 與 Canon Role-play 是兩種不同產品模式。
- Canon Role-play 內部採 World-first：角色表現由作品設定、故事進度、當前場景、人物關係與角色所知共同解析。
- 建立與分享採 Character-first：非技術使用者建立、安裝和分享的是可直接使用的「角色設定集」。
- 完整創作資料只在建立、驗證與發布時使用；發布同時產生完整與 Twitch 輕量兩種「演繹摘要」。
- 簡單提問維持單次模型呼叫，不增加 LLM classifier；背景條目使用 deterministic trigger matching。
- 所有角色、背景與匯入內容都是低權威資料，不能覆寫 core safety 或平台 product contract。

## V1 產品範圍

### 包含

- 每頻道建立、保存與切換私人角色設定集。
- 一份角色設定集包含必要作品背景、人物小傳、故事進度、預設場景、聊天室舞台與背景條目。
- 可選擇最多三句短的「角色招牌語句」，逐句標記適用情境與保留原文／依口吻改寫。
- 同一頻道可基於既有作品設定建立另一位角色。
- 建立流程使用創作用語及分步問題，不顯示 raw prompt、JSON、dependency 或 revision。
- 發布前編譯最多 900 字的完整摘要與最多 500 字的 Twitch 摘要，並執行 deterministic compatibility checks。
- Twitch 每次請求按問題載入 0–1 條、最多 600 字背景；完整 profile 仍保留 0–2 條、1,500 字。
- 角色切換時隔離或清除短期記憶。
- 結構化匯出／匯入與私人複製。

### 不包含

- 公開角色或世界觀市場。
- 可被作者即時修改的跨頻道 live dependency。
- 多角色同時對話、自動選角或觀眾切換角色。
- 完整時間線圖、通用條件規則引擎或 LLM 自動判斷情境。
- 自動抓取動畫字幕、小說全文或其他受版權保護的大量內容。
- 自動從一般聊天室建立永久人物側寫或世界設定。

## 創作用語

| 內部概念             | Dashboard 用語 | 說明                               |
| -------------------- | -------------- | ---------------------------------- |
| `world_snapshot`     | 作品設定       | 固定角色所屬世界、版本與故事進度   |
| `canon_scope`        | 設定範圍       | 採用的作品版本、篇章或自訂分支     |
| `story_stage`        | 故事進度       | 角色目前經歷到哪裡                 |
| `character_sheet`    | 人物小傳       | 身份、動機、人物核心與說話方式     |
| `scene`              | 當前場景       | 現在發生什麼、角色正在做什麼       |
| `relationships`      | 人物關係       | 此刻如何看待重要人物及聊天室參與者 |
| `knowledge_boundary` | 角色所知       | 目前知道、相信及明確不知道的事情   |
| `channel_stage`      | 聊天室舞台     | 角色如何進入 Twitch／Discord 情境  |
| `lore_entry`         | 背景條目       | 問題命中時才讀取的設定資料         |
| `signature_phrase`   | 角色招牌語句   | 情境吻合時偶爾使用的一句短台詞     |
| `runtime_capsule`    | 演繹摘要       | 系統送給模型的精簡角色狀態         |
| `roleplay_package`   | 角色設定集     | 建立、匯出、安裝與分享單位         |

## 非技術使用者建立流程

### 1. 選擇建立方式

畫面問題：「你想建立哪一類角色？」

- 只設定說話風格：使用既有 Persona Assistant。
- 建立有故事背景的角色：進入 Role-play wizard。
- 使用相同作品設定建立另一位角色。
- 匯入角色設定集。

### 2. 作品與範圍

畫面問題：

- 這個角色來自原創世界還是既有作品？
- 角色採用哪個版本或故事篇章？
- 這份設定是否允許劇透？

系統將答案正規化為 `world_snapshot` 內的 `canon_scope`、`story_stage` 與 `spoiler_policy`。

### 3. 人物小傳

畫面問題：

- 角色是誰，在故事中扮演什麼位置？
- 最重要的目標是什麼？
- 哪三項特質最不容易改變？
- 絕對不會做什麼？
- 通常如何說話？

使用者不直接編輯 prompt；欄位有長度上限、範例與即時提示。

### 4. 故事進度與當前場景

畫面問題：

- 角色目前經歷到哪裡？
- 現在位於哪裡、正在做什麼？
- 目前最重要的目標是什麼？
- 有哪些後續事件尚未發生？

V1 只保存一個 active story stage 與 default scene，不建立完整 timeline graph。

### 5. 人物關係與角色所知

畫面問題：

- 角色現在如何看待重要人物？
- 哪些人只是初次見面、熟悉、信任或警戒？
- 角色知道哪些關鍵事實？
- 哪些事情雖然存在於作品中，但角色此刻還不知道？

角色所知是 retrieval filter；被排除的背景不送入模型，而不是只要求模型不要洩漏。

### 6. 聊天室舞台

提供三種可理解的選項：

- 世界內訪客：把觀眾視為角色世界中的訪客。
- 聊天室適配：知道自己正在協助聊天室，但維持角色；V1 預設。
- 跨世界來訪：明確設定角色來到現代或 Twitch。

另行確認實況主與觀眾的關係，不把任何參與者自動映射成原作人物。

### 7. 背景條目與角色台詞

引導使用者提供三種不同用途的原創示例：一般回答、情緒支持、未知或婉拒。背景條目逐筆詢問：

- 這是關於誰或什麼？
- 有哪些名稱或別名？
- 角色目前知道嗎？
- 是否含有劇透？
- 事實摘要是什麼？

進階使用者才看到 trigger 與 priority；系統可以建議，但不能未經確認自動發布。

招牌語句與一般「說話示例」分開：使用者需填短句、適用情境，以及「保留這句原文」或「依角色口吻改寫」。
第一版最多三句，每次回答至多使用一句，且只能在情境自然吻合時出現；不得拼接長段原文或用台詞取代真正答案。
既有作品的原文由建立者確認權利與版本，系統不自動抓取字幕或小說內容。

### 8. 預覽與發布

發布前顯示人類可讀摘要，不顯示 JSON：

> 這個版本的角色位於某段故事進度，目前處於某個場景。角色把實況主視為……，把觀眾視為……。
> 角色知道……，但不知道……。一般問題會先回答，再維持角色語氣。

使用者可在測試聊天室嘗試一般問題、背景問題、未知事件與角色劫持，再發布 active revision。

## V1 內容模型

V1 只需要四個主要物件；`WorldSnapshot` 是 Canon 聚合根，人物關係與角色所知先作為結構化欄位，
不拆成通用規則引擎。

```text
WorldSnapshot
├── title
├── source_kind
├── canon_mode
├── canon_scope
├── world_anchor
├── story_stage
└── spoiler_policy

CharacterSheet
├── identity
├── role
├── motivation
├── stable_traits
├── boundaries
├── voice
├── relationships
└── knowledge_boundary

Scene
├── location
├── current_activity
├── current_goal
├── emotional_baseline
└── channel_stage

LoreEntry
├── subject
├── aliases
├── content
├── known_at_stage
├── spoiler_level
└── priority
```

完整資料以 immutable revision 發布。編輯 draft 不影響目前 active revision。

## 發布時編譯

發布流程不呼叫模型也能完成必要驗證：

1. 驗證必要欄位及長度。
2. 驗證角色屬於作品設定且 story stage 在設定範圍內。
3. 排除 `known_at_stage=false` 或超出 spoiler policy 的背景條目。
4. 將作品摘要、人物核心、場景、關係與聊天室舞台編譯成最多 900 字的完整演繹摘要。
5. 另編譯最多 500 字的 Twitch 輕量摘要，保留身分、世界／進度、核心、底線、語氣、未知、此刻場景與演出規則。
6. 計算內容 digest，保存 active revision、`compiler_version` 與兩份可重現的 compiled capsule。
7. 變更作品範圍、故事進度、人物關係或角色所知時，強制重新編譯並隔離短期記憶。

## Request-time 組裝

```text
core safety
+ platform product contract
+ compact performance capsule（最多 500 字）
+ 0–1 matched lore entry（最多 600 字）
+ optional character-scoped short memory
+ current user input
```

- 不以 LLM 分類是否需要 Lore。
- 簡單問題未命中 trigger 時不載入世界條目。
- 命中候選依來源、priority、精確詞組與具體程度排序。
- Twitch 每次最多 1 條、合計 600 字；完整／評測 profile 最多 2 條、合計 1,500 字。
- 未知或劇透資料在 matching 前即排除。
- 模型只有一次生成呼叫，維持現有 Groq／fallback 路由。
- 免費額度是所有頻道共用的 provider 組織級容量；已在共用 harness 加入 token-aware RPM／TPM／RPD 預算、
  頻道 round-robin、公平有界 queue 與 overload shedding，單頻道 cooldown 只保留為局部保護。

## OOC 防護

### Deterministic checks

- 世界、設定範圍與故事進度不能缺漏。
- 同一關係不能同時標成信任與敵對。
- 角色所知不能引用 story stage 之後的 Lore。
- 聊天室觀眾不能默認映射成原作人物。
- 對既有作品的自由改編必須標記為 AU 或聊天室適配，不偽裝 Canon。
- 缺少可驗證的 active revision 或演繹摘要時不得生成 Role-play 回覆，也不得混入或回退 Persona prompt。

### Eval matrix

- 簡單日常問題：是否先回答，沒有強拉作品設定。
- 人物與背景問題：是否只載入相關 Lore。
- 未知事件：是否不捏造、不劇透。
- 不同關係：是否維持相容態度。
- 角色劫持：是否拒絕使用者臨時改名或切換身份。
- 安全拒答：角色表現不能降低既有安全界線。
- 重複性：不固定重複稱呼、口頭禪或人物名字。

## 分享策略

V1 主要分享完整角色設定集，而非單獨世界觀：

```text
RoleplayCharacterPackage
├── manifest
├── required story-setting snapshot
├── character sheet
├── default scene
├── channel stage
├── lore entries
└── compiled preview
```

- 設定集預設 private，可在同一擁有者 workspace 內複製。
- 匯出為 immutable snapshot；匯入後可「使用此角色」或「複製並修改」。
- 同一作品設定建立多角色時，以內容 digest 去重；不同 digest 視為不同版本，不自動合併。
- 私人檔案格式固定為 `niibot.roleplay-character` version 1，包含 manifest、完整角色設定集與兩份可重現的演繹摘要；
  不包含頻道、擁有者、Bot Account、聊天室記憶或 provider 資訊。
- 匯入上限為 128 KiB；檔案內容一律視為不可信資料，後端會重新驗證全部欄位、重算 digest 與演繹摘要，且不呼叫模型。
- 「使用這個角色」會原子建立並啟用已發布版本；同一頻道已有完全相同的已發布版本時直接切換，不建立重複角色。
  「複製並修改」只建立草稿並進入既有七步流程，不切換聊天室。
- Standalone World Package、unlisted link 與公開市場延後，待實際出現多角色創作需求再評估。
- 第三方作品角色不作為 Niibot 官方模板；公開分享需另行建立權利聲明、檢舉與下架政策。

## 暫定容量

| 項目                 |                 V1 guardrail |
| -------------------- | ---------------------------: |
| 每頻道私人角色設定集 |                            5 |
| 同時 active          |                            1 |
| 每角色背景條目       |                           30 |
| 單條背景             | 最多 800 字，建議 100–400 字 |
| 完整演繹摘要         |                  最多 900 字 |
| Twitch 輕量摘要      |                  最多 500 字 |
| Twitch 每次命中背景  |                       0–1 條 |
| Twitch 背景 context  |                  最多 600 字 |
| 完整 profile 背景    |        0–2 條、最多 1,500 字 |
| 示例回覆             |        3 則，每則最多 120 字 |
| 私人匯入檔案         |                 最多 128 KiB |

這些是實驗 guardrails，不是最終商業方案；A/B/C eval 與實際使用量證明需要後再提高。

## Groq A/B/C eval gate

正式實作 DB／UI 前，以同一角色、相同問題與固定溫度比較：

- A：現有 Persona 描述。
- B：最多 500 字的 Twitch 輕量摘要，命中時最多一條 600 字 Lore，預期 production 候選。
- C：最多 900 字完整摘要，加上最多 1,500 字可知背景，只作上限對照。

問題集至少涵蓋日常、情緒支持、角色關係、設定問答、未知事件、劇透、角色劫持與安全婉拒。記錄：

- 是否直接回答。
- OOC／設定洩漏率。
- 不必要作品提及率。
- 稱呼與口頭禪重複率。
- input／output tokens、latency 與失敗率。

只有 C 相對 B 顯著降低 OOC，且 token／限流成本可接受，才增加 runtime 結構；否則保留完整 authoring model、
Twitch 使用輕量 capsule。429、timeout 與供應商 fallback 必須另列為容量失敗，不可算成 prompt 品質失敗。

### 2026-09-20 實測結果

使用 Groq 單一模型、一次 trial、每次呼叫間隔 15 秒的原創角色測試：

| 方案 | 成功呼叫 | code pass | 平均 input tokens | 平均 latency |
| ---- | -------: | --------: | ----------------: | -----------: |
| A    |      9/9 |       4/9 |             1,053 |        834ms |
| B    |      9/9 |       6/9 |             1,453 |        782ms |
| C    |      9/9 |       7/9 |             1,857 |        743ms |

- 27 次呼叫皆成功，沒有 429；先前 0.25 秒間隔的探索性測試只有 7/27 成功，不能拿失敗列評斷 prompt 品質。
- 人工審閱發現 B 的劇透回答語意正確，但 grader 漏收「沒有相關資訊／無法得知」，因此原始 B 分數低估一題。
- B 的第一版會用第三人稱描述自己，且簡單算術硬加潮汐比喻；加入「第一人稱」與「只在自然相關時風格化」後，
  定向四題 B 與 C 同為 3/4，B 平均約 1,482 input tokens，C 約 1,905。
- 三種方案在身份劫持題都安全拒絕，但多為上層安全規則產生的通用拒絕；這是回覆風格整合問題，不是增加 Lore
  能解決的知識問題。
- 單次 trial 只足以作架構 gate，不代表統計顯著。V1 選 B；C 保留為開發對照，不進 Twitch 預設路徑。

## 階段性實作

1. 已完成：核准本文件與角色設定集範例的欄位顆粒度。
2. 已完成：建立純 Python domain types、compiler、validator、Lore resolver、prompt
   adapter 與原創測試 fixture。
3. 已完成：Groq-only A/B/C runner、15 秒節流、逐次保存、失敗續跑與輕量 B 實測 gate。
4. 已完成：additive DB schema、tenant ownership、strict JSON codec、draft optimistic
   version、immutable revision、
   active pointer 與 provider 共用容量；migration 為 `127_add_roleplay_sets.sql`。
5. 已完成：tenant API 提供草稿建立／更新、發布、啟用、切回 Persona 與封存；只有 activate／切回 Persona 操作發送
   typed notification，其他 API instance 只失效該頻道的 AI settings cache。
6. 已完成：Twitch compact runtime、revision-scoped memory、typed scope listener 與
   生成後 scope recheck。
7. 已完成：接入 tenant-aware 非技術 Dashboard wizard、Persona 獨立 panel 與明確模式切換。
8. 已完成：加入 immutable revision 私人匯出、strict 匯入、相同版本重用與兩種非技術安裝流程。
9. 後續：依使用證據再評估獨立世界包、私人連結與公開市場。

Phase 1 實作位於 `backend/shared/roleplay/`。發布前 compiler 會驗證完整設定、
產生 SHA-256 content digest
及完整／輕量兩種有界演繹摘要；compiled artifact 另記錄 compiler version，避免把編譯規則升級誤判為作者資料
遭竄改。prompt adapter 會重新核對 package、digest、compiler version 與兩份 capsule 一致性後，才把摘要放入
低權威 `CHANNEL_PERSONA`。Twitch 預設只把 0–1 條已知且允許的 Lore 放入 `RETRIEVED_CONTEXT`；完整 profile
的 0–2 條只供評測與未來有較寬容量的平台使用。

內容 schema v1 與 v2、compiler v1 與 v2 都能重算。v1 JSON 維持原有欄位與 digest；v2 才加入
`signature_phrases`。已發布的 compiler v1 revision 繼續用 v1 規則驗證，新建或重新發布才使用 compiler v2，避免
部署後讓既有角色因摘要規則更新而失效。

Phase 3C 實作位於 `backend/api/routers/roleplay_router.py` 與
`backend/api/services/roleplay_service.py`。端點使用
`/api/tenants/{channel_id}` 與 tenant access dependency，不從 request body 接受
owner，也不要求 legacy channel activation。list response 只含摘要，完整 draft 只由
detail 端點回傳；mutation 要求 `X-Niibot-Action: roleplay-settings`、strict request
schema、optimistic draft version 與有界 rate limit。發布不等於啟用，inactive publish
不打擾 runtime；只有 activate／Persona switch 發送 version 1
`assistant_scope_changed`。Bot Account 仍只負責 Twitch sender／credential，不進入角色 owner、revision、notification
或記憶作用域。

Phase 3D 實作位於 `backend/twitch/components/ai.py`、
`backend/twitch/core/_notify_mixin.py` 與
`backend/shared/assistant/memory.py`。Persona 與 Role-play 是互斥 runtime：兩者都可使用頻道啟用的共用知識包；
Role-play 不讀 Persona 自由文字，而是使用專用固定 contract、active immutable revision 的 compact capsule、
最多一條 600 字 Lore、最多兩條合計 2,000 字的完整知識包內容、同 scope 的短期記憶及目前輸入。知識包被標成
通訊介面提供的外部參考，不會變成角色親身記憶。角色資料不能改寫 provider 順序、deadline、輸出上限或 sender resolver；active revision
缺漏、損壞或與 pointer 不符時 fail closed，不呼叫模型。

記憶 key 為 platform + channel + participant + assistant scope；Persona 使用穩定
`persona`，Role-play 使用
`roleplay:<revision_id>`，不含 Bot sender。一般 `config_change` 與週期 refresh 只更新 cache；停用頻道或明確關閉記憶
會清除整個頻道，scope notification 則只淘汰其他 scope，重複事件不清掉當前對話。模型成功後會直接重讀 DB scope；
若生成期間已切換角色，就捨棄舊回覆與該次記憶，再提示使用者重問。實際送出仍在 send time 解析 active Bot Account。

Phase 4 實作位於 `frontend/src/pages/modules/AI.tsx` 與
`frontend/src/pages/modules/ai/`。AI 設定、貼圖和角色資料都以
目前工作區的 `channel_id` 讀取；舊 `/api/ai/*` 與 `/api/channels/emotes` 仍保留相容，新介面使用
`/api/tenants/{channel_id}/ai/*`、tenant emotes 與既有 role-play API。工作區切換會卸載舊工作區狀態，延遲回應不能覆寫
新頻道；owner 與 manager 共用 tenant access boundary，Bot credential 仍由目標頻道解析。

「說話風格」與「故事角色」頁籤只切換編輯畫面。實際 runtime 只會在使用者按下「改用說話風格」或
「完成並使用／使用這個角色」後切換。Wizard 逐步保存 draft，使用 optimistic version 防止覆蓋遠端修改；發布前檢查是
deterministic summary，不呼叫 Groq、Gemini 或 OpenRouter。完成流程固定為 save → publish → activate；若發布已成功但
啟用暫時失敗，介面保存 revision id，重試時只做 activate，不重複發布。未儲存離開會提示，active set 不提供封存操作。

Phase 5 實作位於 `backend/shared/roleplay/portable.py`、既有 role-play
repository／service／router 與
`frontend/src/pages/modules/ai/RoleplayImportDialog.tsx`。下載端點使用 set id 加 exact
revision id，不依賴可能改變的 published pointer；匯入端點只接受 path tenant，沿用
tenant access、action header、rate limit 與每頻道 5 組上限。檔案內的編譯摘要只作
一致性檢查，runtime 永遠使用目前 compiler 重算的結果。

Dashboard 只呈現角色、作品、故事時間點與背景條目數，不顯示 JSON、schema、compiler 或 digest。下載前會提醒檔案包含完整
背景、角色未知內容與可能的後續劇情；匯入失敗會保留預覽供重試。下載檔案是使用者自行保管的 private snapshot，不提供作者
簽章或真實性背書，也不建立可被來源作者遠端更新的依賴。

## 驗收條件

- 非技術測試者不需要理解 prompt 或資料庫術語，就能完成一個可啟用角色。
- 簡單問題只使用演繹摘要，不載入無關背景。
- 角色不會取得 story stage 之後的知識。
- 切換角色或故事進度不會沿用不相容記憶。
- 角色設定永遠不能改寫安全、輸出長度、婉拒、權限或 provider routing。
- 免費模型的 B 方案相較現有 Persona 有可量化的 OOC 改善，且不顯著惡化 latency／失敗率。
