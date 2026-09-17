# Role-play 角色系統 V1 規劃

## 文件狀態

本文件是產品與架構決策草案，用來確認範圍及驗證角色設定集格式。V1 尚未進入 DB、API、prompt compiler
或 Dashboard 實作。

## 核心決策

- Persona Assistant 與 Canon Role-play 是兩種不同產品模式。
- Canon Role-play 內部採 World-first：角色表現由作品設定、故事進度、當前場景、人物關係與角色所知共同解析。
- 建立與分享採 Character-first：非技術使用者建立、安裝和分享的是可直接使用的「角色設定集」。
- 完整創作資料只在建立、驗證與發布時使用；runtime 讀取編譯後的精簡「演繹摘要」。
- 簡單提問維持單次模型呼叫，不增加 LLM classifier；背景條目使用 deterministic trigger matching。
- 所有角色、背景與匯入內容都是低權威資料，不能覆寫 core safety 或平台 product contract。

## V1 產品範圍

### 包含

- 每頻道建立、保存與切換私人角色設定集。
- 一份角色設定集包含必要作品背景、人物小傳、故事進度、預設場景、聊天室舞台與背景條目。
- 同一頻道可基於既有作品設定建立另一位角色。
- 建立流程使用創作用語及分步問題，不顯示 raw prompt、JSON、dependency 或 revision。
- 發布前編譯 600–900 字的演繹摘要並執行 deterministic compatibility checks。
- 每次請求按問題載入 0–2 條背景條目。
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
| `story_setting`      | 作品設定       | 角色所屬世界與必要規則             |
| `canon_scope`        | 設定範圍       | 採用的作品版本、篇章或自訂分支     |
| `story_stage`        | 故事進度       | 角色目前經歷到哪裡                 |
| `character_sheet`    | 人物小傳       | 身份、動機、人物核心與說話方式     |
| `scene`              | 當前場景       | 現在發生什麼、角色正在做什麼       |
| `relationships`      | 人物關係       | 此刻如何看待重要人物及聊天室參與者 |
| `knowledge_boundary` | 角色所知       | 目前知道、相信及明確不知道的事情   |
| `channel_stage`      | 聊天室舞台     | 角色如何進入 Twitch／Discord 情境  |
| `lore_entry`         | 背景條目       | 問題命中時才讀取的設定資料         |
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

系統將答案正規化為 `story_setting`、`canon_scope` 與 `spoiler_policy`。

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

### 7. 說話示例與背景條目

引導使用者提供三種不同用途的原創示例：一般回答、情緒支持、未知或婉拒。背景條目逐筆詢問：

- 這是關於誰或什麼？
- 有哪些名稱或別名？
- 角色目前知道嗎？
- 是否含有劇透？
- 事實摘要是什麼？

進階使用者才看到 trigger 與 priority；系統可以建議，但不能未經確認自動發布。

### 8. 預覽與發布

發布前顯示人類可讀摘要，不顯示 JSON：

> 這個版本的角色位於某段故事進度，目前處於某個場景。角色把實況主視為……，把觀眾視為……。
> 角色知道……，但不知道……。一般問題會先回答，再維持角色語氣。

使用者可在測試聊天室嘗試一般問題、背景問題、未知事件與角色劫持，再發布 active revision。

## V1 內容模型

V1 只需要四個主要物件；人物關係與角色所知先作為結構化欄位，不拆成通用規則引擎。

```text
StorySetting
├── title
├── source_kind
├── canon_scope
├── world_anchor
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
├── story_stage
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
4. 將作品摘要、人物核心、場景、關係與聊天室舞台編譯成 600–900 字演繹摘要。
5. 計算內容 digest，保存 active revision 與可重現的 compiled capsule。
6. 變更作品範圍、故事進度、人物關係或角色所知時，強制重新編譯並隔離短期記憶。

## Request-time 組裝

```text
core safety
+ platform product contract
+ compiled performance capsule
+ 0–2 matched lore entries
+ optional character-scoped short memory
+ current user input
```

- 不以 LLM 分類是否需要 Lore。
- 簡單問題未命中 trigger 時不載入世界條目。
- 命中候選依來源、priority、精確詞組與具體程度排序。
- 每次最多 2 條、合計 1,500 字；未知或劇透資料在 matching 前即排除。
- 模型只有一次生成呼叫，維持現有 Groq／fallback 路由。

## OOC 防護

### Deterministic checks

- 世界、設定範圍與故事進度不能缺漏。
- 同一關係不能同時標成信任與敵對。
- 角色所知不能引用 story stage 之後的 Lore。
- 聊天室觀眾不能默認映射成原作人物。
- 對既有作品的自由改編必須標記為 AU 或聊天室適配，不偽裝 Canon。
- 缺少可編譯演繹摘要時不得啟用 Role-play，回退一般助手。

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
- Standalone World Package、unlisted link 與公開市場延後，待實際出現多角色創作需求再評估。
- 第三方作品角色不作為 Niibot 官方模板；公開分享需另行建立權利聲明、檢舉與下架政策。

## 暫定容量

| 項目                 |                 V1 guardrail |
| -------------------- | ---------------------------: |
| 每頻道私人角色設定集 |                            5 |
| 同時 active          |                            1 |
| 每角色背景條目       |                           30 |
| 單條背景             | 最多 800 字，建議 100–400 字 |
| 演繹摘要             |                   600–900 字 |
| 每次命中背景         |                       0–2 條 |
| 每次背景 context     |                最多 1,500 字 |
| 示例回覆             |        3 則，每則最多 120 字 |

這些是實驗 guardrails，不是最終商業方案；A/B/C eval 與實際使用量證明需要後再提高。

## Groq A/B/C eval gate

正式實作 DB／UI 前，以同一角色、相同問題與固定溫度比較：

- A：現有 Persona 描述。
- B：600–900 字演繹摘要，預期候選。
- C：完整 1,500 字 Role Context 加更多背景。

問題集至少涵蓋日常、情緒支持、角色關係、設定問答、未知事件、劇透、角色劫持與安全婉拒。記錄：

- 是否直接回答。
- OOC／設定洩漏率。
- 不必要作品提及率。
- 稱呼與口頭禪重複率。
- input／output tokens、latency 與失敗率。

只有 C 相對 B 顯著降低 OOC，才增加 runtime 結構；否則保留完整 authoring model、使用精簡 capsule。

## 階段性實作

1. 核准本文件與角色設定集範例的欄位顆粒度。
2. 建立純 Python domain types、compiler、validator 與原創測試 fixture。
3. 執行 Groq-only A/B/C 合成 eval，不使用第三方角色資料作 repository 測試資產。
4. 設計 additive DB schema、tenant ownership、draft／active revision 與記憶隔離。
5. 實作 API 與非技術 wizard。
6. 加入私人匯出／匯入；依使用證據再評估分享與公開市場。

## 驗收條件

- 非技術測試者不需要理解 prompt 或資料庫術語，就能完成一個可啟用角色。
- 簡單問題只使用演繹摘要，不載入無關背景。
- 角色不會取得 story stage 之後的知識。
- 切換角色或故事進度不會沿用不相容記憶。
- 角色設定永遠不能改寫安全、輸出長度、婉拒、權限或 provider routing。
- 免費模型的 B 方案相較現有 Persona 有可量化的 OOC 改善，且不顯著惡化 latency／失敗率。
