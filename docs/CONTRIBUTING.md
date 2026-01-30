# Git Commit Message 規範

本專案採用 **Conventional Commits**
規範，以確保提交紀錄的**一致性、可讀性與自動化支援能力**。

---

## 1. 提交格式

```text
<type>(<scope>): <subject>
```

- `type`：提交類型（必填）
- `scope`：影響模組（選填）
- `subject`：本次變更的簡短說明（必填）

### 範例

```bash
feat(api): 新增 webhook 驗證機制
fix(frontend): 修正登入按鈕無法點擊
docs: 更新專案安裝說明
```

---

## 2. 類型說明（Types）

類型 說明

---

- feat 新增功能
- fix 修正錯誤
- docs 文件變更
- style 程式碼格式調整（不影響邏輯）
- refactor 程式碼重構
- perf 效能優化
- test 測試相關
- chore 工具、設定、雜務

---

## 3. 撰寫規則

- `type` 一律小寫
- 冒號後需空一格：`type: subject`
- `subject` 簡潔明確，建議不超過 50 字
- 使用現在式祈使句（add / fix / update）

### 正確範例

```bash
feat: 新增登入流程
fix(api): 修正 token 過期處理
```

### 錯誤範例

```bash
Add login feature     ❌ 無 type
FIX: 修 bug           ❌ type 大寫
feat:add api          ❌ 冒號後無空格
```

---

## 4. Scope 使用建議

專案為多模組架構時，建議加上 scope：

```bash
feat(frontend): 新增 Dark Mode
fix(api): 修正 JWT 驗證邏輯
```

---

## 5. 快速選擇指南

變更內容 使用類型

---

- 新功能 feat
- 修 bug fix
- 改文件 docs
- 調整格式 style
- 重構 refactor
- 效能優化 perf
- 新增測試 test
- 工具 / 設定 chore

---

## 6. 標準提交範本

```text
feat(scope): 簡短描述本次變更
```

```text
fix(api): 修正 webhook 驗證錯誤
```
