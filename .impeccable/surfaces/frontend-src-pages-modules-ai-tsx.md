---
version: 1
slug: "frontend-src-pages-modules-ai-tsx"
primary_target: "frontend/src/pages/modules/AI.tsx"
related_targets: ["frontend/src/pages/modules/ai"]
---

# AI Assistant Dashboard direction contract

THESIS: 讓非技術實況主像整理人物設定卡一樣建立角色；拒絕把完整 schema 攤成單頁技術表單。

OWN-WORLD: 沿用 Niibot 紫色語意色、亮暗主題、12–16px 圓角、克制卡片與既有 Button／Input／Tabs；色彩只標示主要動作、選取與狀態。

STORY: 使用者先辨認目前實際模式，再選擇編輯說話風格或故事角色；逐步補足作品、人物、場景與知識，檢查後明確啟用。

FIRST VIEWPORT: PageHeader 下先放目前模式與兩個編輯入口；角色頁先顯示清單／空狀態與單一「建立故事角色」主動作，進入編輯後桌面為步驟導覽加單一內容區，窄版改為頂部進度。

FORM: 既有 AI 頁的局部延伸（1/1）；Operate、列表進入七步 wizard；seed: not-required-local-extension。

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review and verdict. No new raster ships
in this surface.
