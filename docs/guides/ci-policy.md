# CI 用量與驗證政策

Niibot 是公開版本庫。公開 Repo 使用標準 GitHub-hosted runner 不計 Actions 分鐘，self-hosted runner
也不計 Actions 分鐘；larger runner、artifact／cache storage 仍依 GitHub 方案計費。CI 的主要目標是縮短
可信結果的等待時間，同時保留合併與部署安全。

## Runner 與用量原則

- GitHub-hosted job 使用標準 `ubuntu-latest`；未經成本評估不得改用 larger runner。
- runner-minutes 仍作為效能趨勢指標，但不是此公開 Repo 的 2,000 分鐘 private-repo 配額。
- Artifact 與 cache 只保留驗證所需內容與期間；public Repo 免費 runner 不代表 storage 無限制。
- self-hosted runner 只承擔受 Environment 保護的部署，不執行 fork／PR code。
- 若 Repo 改回 private，必須重新建立帳號層級分鐘預算與 50%／75%／90% 警戒線。

計費依據見 [GitHub Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions)。

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

Frontend 的 80% 是 `frontend/vitest.config.ts` 明列模組的 **critical-module coverage gate**，不是整個
`frontend/src` 的全域 coverage。新增關鍵 auth、stream、cache 或資料轉換模組時，應同步加入 include 清單；
不得把這個數字描述為全產品前端覆蓋率。Backend coverage 則由完整 `backend/tests` suite 合併計算。

## 變更分類契約

分類由 [`scripts/ci/paths.py`](../../scripts/ci/paths.py) 管理並以 table-driven tests 固定：

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
- Backend pytest 使用 quiet progress，避免 4,000+ tests 的逐筆 log I/O；失敗保留 short traceback，並輸出
  最慢 30 個測試供後續 fixture／query 優化。

不要為了縮短 wall-clock 把測試任意拆成更多 GitHub-hosted jobs。每個 job 都有 checkout／setup 成本，
且不足一分鐘仍以一分鐘計費。若需平行化，先評估同一 runner 內的 test workers，並確保資料庫按 worker 隔離。

## 安全與可重現性

- Workflow 權限預設只有 `contents: read`；需要額外權限時按 job 明列。
- Repository Actions policy 只允許 GitHub 官方 action、`astral-sh/setup-uv` 與
  `gitleaks/gitleaks-action`，並強制完整 commit SHA；行尾保留 release tag 供 Dependabot 與人工閱讀。
- 部署 CVE scanner 固定 Trivy 版本與 multi-arch digest，不可使用 mutable `latest`。
- Fork／PR code 不可在具 production 或 deployment credentials 的 self-hosted runner 執行。
- Dependency cache 只加速安裝，不可拿 cache 取代 lockfile 或完整 protected-branch verification。
- Secret scan 即使在 Draft 與 docs-only PR 仍必須執行。

## Branch rulesets

截至 2026-09-29，default branch 是 `main`，並有兩個 active repository ruleset：

- `main`：禁止刪除與 non-fast-forward update，只允許 PR merge；要求
  `Preflight (Secrets, Env & Scope)`、`Frontend Lint & Build`、`Backend Lint & Test` 與
  `Deploy Staging / Deploy to staging`。單人維護階段不要求 approval，但 discussion 必須 resolved。
- `staging`：禁止刪除與 non-fast-forward update，PR 要求 Preflight／Frontend／Backend 三項檢查；
  維護者 `yPinn` 有明確 always bypass，保留 solo direct-push 流程。其他 actor 不可繞過。

Ruleset 的可用性與行為見 [GitHub rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)。
變更 job display name 前，必須先同步 required status context，避免鎖死 promotion；不得用關閉 ruleset
作為日常 workaround。

## 可貼給其他 Repo session 的調整規格

```text
請先量測這個 Repo 最近成功／失敗 CI 的 job 與 step runner-minutes，再依下列原則調整，
不要直接複製 Niibot 的路徑：

1. 先確認 Repo visibility與runner種類；private-repo分鐘跨帳號共用，public標準runner則以等待時間與storage為主。
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
