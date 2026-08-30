# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Niibot 服務有直播與社群營運需求的實況主，不以經營階段或單一使用情境限縮受眾。使用者依自己的
頻道需求選用 Twitch、Discord、OBS overlay、互動與管理功能。

## Product Purpose

Niibot 將直播聊天室、社群伺服器與 Web Dashboard 的日常管理集中在同一套系統，協助實況主處理
重複性工作、維持觀眾互動，並把注意力留在直播內容本身。成功代表使用者能快速找到所需功能，
理解它如何融入直播流程，並從首頁直接開始使用。

## Positioning

同一套 Niibot 系統同時連接 Twitch Bot、Discord Bot、Web Dashboard 與 OBS overlay；功能以模組化
方式覆蓋不同頻道需求，而不是要求所有實況主採用同一套固定流程。

## Operating Context

- 使用者從公開 Landing Page 了解功能，透過頂部主要 CTA 進入登入／開始使用流程。
- 登入後在 Web Dashboard 管理指令、事件、排隊、AI、分析與其他模組。
- Video Queue 接收聊天、Twitch 點數兌換或主播手動加入的影片，並透過 OBS browser source 播放。
- Discord Bot 提供社群連結預覽、事件日誌與娛樂互動等能力。

## Capabilities and Constraints

- Twitch 功能包含自訂指令與觸發器、事件自動回應、定時訊息、遊戲與影片排隊、分析、AI、準星收藏與贊助。
- Video Queue 支援 YouTube、Bilibili 與 Twitch Clip，可限制佇列、每人投稿、冷卻、觀看數與影片長度，
  並支援排序、插播、跳過、清空與 OBS overlay。
- Discord 功能包含社群連結預覽、伺服器事件日誌、娛樂／占卜、生日與抽獎。
- 現況沒有可對外宣稱的 Video Queue 設定模板匯入能力；Landing 的模板式內容只作產品流程展示。
- Landing 不直接掛接任何使用者的 live Video Queue overlay；展示必須隔離於真實 username、polling 與
  advance API。若改為實際影片播放，來源需是專用且可自有託管的靜音 demo clip。

## Brand Commitments

- 產品名稱為 Niibot，中文稱呼與人格為「泥爸」。
- 文案可保留「沒有勞基法保障的虛擬社畜」等自嘲、直接、有親和力的品牌語氣，但功能說明必須清楚且可信。
- 沿用專案現有 `Avatar.png`、圓角介面、紫色主色、亮／暗色主題與既有 semantic design tokens。

## Evidence on Hand

- 真實前端管理畫面與互動位於 `frontend/src/pages`、`frontend/src/components`。
- Niibot 頭像位於 `frontend/src/assets/images/Avatar.png`。
- Video Queue Dashboard、OBS overlay 與 API 型別可作為 Landing 展示的真實產品依據。
- 目前沒有已確認的使用者數據、客戶 logo、見證、成效指標或可宣稱的模板庫；未來首頁不得捏造。

## Product Principles

- 讓使用者先看見能解決的需求，再決定採用哪些模組。
- 用真實產品流程與畫面取代抽象功能堆疊。
- 主要行動保持直接，產品介紹不阻擋開始使用。
- 跨 Twitch、Discord 與 OBS 的能力必須以一套系統的整合價值呈現。
- 所有行銷文案只描述已存在且可驗證的能力。
