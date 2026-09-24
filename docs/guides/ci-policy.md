# CI 用量與驗證政策

Niibot 使用 GitHub Free 私有版本庫。GitHub-hosted Actions 分鐘由帳號下所有私有版本庫共用，
因此 CI 的目標不是讓單次畫面最快，而是在不犧牲合併與部署安全的前提下降低總 runner-minutes。

## 帳號層級原則

目前每月 2,000 分鐘的內部軟配額如下；這不是 GitHub 可強制的 Repo quota，而是營運目標：

| 用途      | 每月目標分鐘 |
| --------- | -----------: |
| Niibot    |        1,200 |
| Utawakui  |          300 |
| ProGrads  |          200 |
| 其他 Repo |          100 |
| 緊急預留  |          200 |

用量狀態：

- 0–50%：正常執行。
- 50–75%：檢視各 Repo 與 job 趨勢。
- 75–90%：停止非必要排程與 Draft 的昂貴測試。
- 90–100%：只保留 Ready PR、staging 與 release 驗證。
- 100%：等待重置，或切到獨立且不具部署憑證的 self-hosted CI runner。

GitHub 內建 included-usage alert 只在 90% 與 100% 通知；50%／75% 必須由本地或
self-hosted 監控。監控不可只依賴 GitHub-hosted runner，否則額度耗盡後監控本身也無法啟動。

## Niibot workflow 拓樸

```text
Preflight (Secrets, Env & Scope)
├─ gitleaks
├─ env registry consistency
└─ changed-path classifier
      ├─ Frontend Lint & Build（需要時）
      └─ Backend Lint & Test（需要時）
                     ↓
       staging push 才可 Deploy Staging
                     ↓
       staging → main promotion 重用相同 tree 的驗證結果
```

Preflight 必須先成功，昂貴測試才可啟動。Secret scan、env check 與 path detection 共用一台
runner，避免三個短 job 分別向上計費。

### 事件矩陣

| 事件／變更                         | Preflight | Frontend | Backend | Coverage | Deploy  |
| ---------------------------------- | :-------: | :------: | :-----: | :------: | :-----: |
| Draft PR                           |     ✓     |    —     |    —    |    —     |    —    |
| Ready PR：docs／root tooling only  |     ✓     |    —     |    —    |    —     |    —    |
| Ready PR：`frontend/**`            |     ✓     |    ✓     |    —    |    —     |    —    |
| Ready PR：`backend/**`             |     ✓     |    —     |    ✓    |    —     |    —    |
| Ready PR：前後端或 CI control path |     ✓     |    ✓     |    ✓    |    —     |    —    |
| 未識別路徑                         |     ✓     |    ✓     |    ✓    |    —     |    —    |
| `staging` push                     |     ✓     |    ✓     |    ✓    |    ✓     | staging |
| `staging` → `main` promotion PR    |     —     |    —     |    —    |    —     |    —    |
| promotion merge 後的 `main` push   |     —     |    —     |    —    |    —     |    —    |
| manual／reusable invocation        |     ✓     |    ✓     |    ✓    |    ✓     |    —    |

以 `staging` 為目標的 PR 仍跑完整受影響套件，只把 coverage 留給 staging push／manual run。這避免
coverage instrumentation 在每個小 commit 重複執行，又保留 staging deploy 前的 80% coverage gate。
`main` 不接受其他來源；promotion PR 與 merge 後 push 的 tree 已由 staging push 驗證並實際部署，因此不再
啟動同一套 CI。若未來允許 direct main push、其他來源 PR 或在 merge 時修改內容，必須先恢復 main 的完整 CI。

## 變更分類契約

分類由 [`scripts/ci_changed_paths.py`](../../scripts/ci_changed_paths.py) 管理並以 table-driven tests 固定：

- `frontend/**` 只要求 Frontend。
- `backend/**` 只要求 Backend；migration、shared 與 auth 自然包含在此範圍。
- `.github/workflows/ci.yml` 或分類器本身屬 CI control plane，要求兩邊都跑。
- docs、Dependabot 設定、root lint／format tooling 與 generated env metadata 可只跑 Preflight。
- 任何未列入的路徑採 conservative fallback，兩邊都跑。
- `staging` push、manual 與 reusable invocation 不看路徑，一律完整執行。

不得把 `paths:` 直接設在需要穩定顯示的整個 workflow 上。GitHub 會讓被 workflow-level path filter
跳過的 required check 保持 Pending；應讓 workflow 固定建立，再以 job-level `if` 產生可見的 skipped result。

## 取消、逾時與失敗順序

- Concurrency 只依 PR number 取消同一 PR 的舊 run；轉回 Draft 也會觸發 Preflight 並取消舊的昂貴 run。
- Staging push 以唯一 run id 分組，不互相取消。
- `_deploy.yml` 保持 `cancel-in-progress: false`；migration 與 restart 不可被新 deploy 中斷。
- Preflight timeout 5 分鐘、Frontend 10 分鐘、Backend 20 分鐘。
- lint、format、type/build 排在測試前，便宜的失敗應先阻止昂貴測試。
- Backend pytest 使用 quiet progress，避免 2,000+ tests 的逐筆 log I/O；失敗保留 short traceback，並輸出
  最慢 30 個測試供後續 fixture／query 優化。

不要為了縮短 wall-clock 把測試任意拆成更多 GitHub-hosted jobs。每個 job 都有 checkout／setup 成本，
且不足一分鐘仍以一分鐘計費。若需平行化，先評估同一 runner 內的 test workers，並確保資料庫按 worker 隔離。

## 安全與可重現性

- Workflow 權限預設只有 `contents: read`；需要額外權限時按 job 明列。
- 外部 Actions 鎖定完整 commit SHA，行尾保留 release tag 供 Dependabot 與人工閱讀。
- Fork／PR code 不可在具 production 或 deployment credentials 的 self-hosted runner 執行。
- Dependency cache 只加速安裝，不可拿 cache 取代 lockfile 或完整 protected-branch verification。
- Secret scan 即使在 Draft 與 docs-only PR 仍必須執行。

## Free private Repo 的 required-check 限制

截至 2026-09-08，GitHub API 對此 private GitHub Free Repo 的 branch protection 回覆需升級方案或公開
Repo，因此 checks 目前是可見訊號，不是平台強制閘門。現行人工規則是「Preflight 或任何已執行測試紅燈時
不得合併」。不要為取得免費 Actions 或 branch protection 而公開非預期公開的原始碼。

未來方案支援 required checks 時：

1. 先在 staging 規則要求穩定存在的 Preflight、Frontend、Backend job 名稱；job-level skipped 視為成功。
2. 只有需要單一 branch-rule context 時才新增彙總 CI Gate。
3. 新增 Gate 前先把它每次至少一分鐘的成本納入帳號配額。

## 可貼給其他 Repo session 的調整規格

```text
請先量測這個 Repo 最近成功／失敗 CI 的 job 與 step runner-minutes，再依下列原則調整，
不要直接複製 Niibot 的路徑：

1. 帳號的 GitHub-hosted private-repo 分鐘跨 Repo 共用；先定義本 Repo 軟配額。
2. 同一 Ready PR 的新 commit 取消舊 CI；protected branch 與 deploy 不得被取消。
3. Draft PR 只跑 secret/config preflight；ready_for_review 必須觸發正式 CI。
4. 合併 sub-minute validation jobs，昂貴 jobs 必須 needs preflight。
5. 使用 tested changed-path classifier；未知路徑 fail safe 為完整測試。
6. 不在 required workflow 使用 top-level paths；改用 job-level conditions 與穩定 check names。
7. targeting-staging PR 跑受影響套件測試；staging push 跑完整 integration + coverage；main promotion 重用結果。
8. 加入依實測 P95 設定的 timeout；便宜的 lint/type failures 排在測試前。
9. 不用多 runner sharding 假裝省額度；先量測 test durations，再評估單 runner 平行化。
10. 外部 Actions pin full SHA；self-hosted CI 必須與 deploy credentials 隔離。
11. 驗證 draft/frontend-only/backend-only/both/docs/unknown/protected-push 的行為矩陣。
12. 交付實測節省、風險、rollback 與一週後的用量觀測方式。
```

## 變更後驗證清單

- YAML 與 GitHub Actions expression lint 通過。
- 路徑分類的 unit test 與 CLI smoke test 通過。
- Draft、frontend-only、backend-only、both、preflight-only、unknown、push 情境皆符合矩陣。
- `npm run env:check` 通過。
- Frontend lint、format、build、無 coverage tests 與 coverage tests 通過。
- Backend ruff、mypy、migration、無 coverage tests 與 coverage gate 通過。
- staging deploy 仍只依賴完整成功的 staging-push CI，且 reusable deploy 的不可取消設定未變。
- staging→main PR 與 promotion merge 後 main push 不建立重複 CI run；其他來源若重新開放必須 fail-safe 回完整驗證。
- 上線一週後比較每 run 平均分鐘、每 Repo 月累積與 cancelled run 節省量。
