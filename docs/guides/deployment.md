# 部署

三個環境、Docker Compose overlay、CI/CD 密鑰同步、版本標記。

Cloudflare Pages Functions 的額度、`_routes.json`、Fail mode 與常駐 Overlay
request budget 見 [cloudflare-pages.md](cloudflare-pages.md)。
GitHub Actions 的共用額度、事件矩陣與安全節流規則見 [ci-policy.md](ci-policy.md)。
Discord 的兩套 Application、Portal 權限與 command promotion 見 [discord.md](discord.md)。

## 分支與環境

| 分支                 | 環境   | 部署方式                                                             |
| -------------------- | ------ | -------------------------------------------------------------------- |
| `main`               | 正式區 | 重用 staging release-candidate 驗證；production 由手動或每週排程部署 |
| `staging`            | 測試區 | 推 `staging` → CI 綠 → 自動部署（`ci.yml`）                          |
| `feature/*`、`fix/*` | 本機   | —                                                                    |

- `deploy-staging.yml` 保留供手動 `workflow_dispatch`（例如臨時起 staging bot 測試）。
- `_deploy.yml` 是共用工作流，caller 只傳 `environment`（`production` \| `staging`）；
  路徑／埠／suffix／預設服務集由內部 `Resolve environment config` step 依環境推導。
- runner 上的 env 檔由 `scripts/env/ci.py` 依 `env.manifest.json` 解析 GitHub
  Secrets／Variables；`scripts/env/write_ci.sh` 是最小化的 workflow wrapper。

一般流程：`feature/xxx` ──PR──▶ `staging` ──完整 CI／coverage／deploy／QA──▶ PR ──▶ `main`。
`staging → main` promotion PR 與 merge 後 main push 不重跑相同 CI；main 不接受其他來源或 direct push。
Hotfix 同樣先進 `staging` 完成驗證與部署，再 promotion 到 `main`，不得先改 main 再 backport。

期望分支規則：`main` 需 PR + 1 approval、禁止直推；`staging` 需 PR、允許 solo 直推。
截至 2026-09-08，此 private Repo 使用 GitHub Free，GitHub API 回覆 branch protection 需升級方案或公開
Repo，因此目前以「CI 紅燈不得合併」的人工作業維持；方案支援後再把上述規則設為平台強制。

## Docker Compose overlay

每個環境固定 project、root env 與 overlay。日常操作使用 `nb stack`，避免漏帶任一參數：

```bash
npm run nb -- stack dev up [profile]
npm run nb -- stack stg up [profile]
npm run nb -- stack prod up [profile]
```

底層一律為 `compose.yaml` + `compose.<dev|stg|prod>.yaml`，project 分別是
`niibot-dev`、`niibot-stg`、`niibot-prod`，root env 為 `.env.<env>`；build image 也分別使用
`-dev`、`-stg`、`-prod` 後綴，避免跨環境覆蓋。

Profile：`api` / `twitch` / `discord` / `bots` / `full`（見 [development.md](development.md)）。

對外埠：

| 服務           |  dev |   stg |  prod |
| -------------- | ---: | ----: | ----: |
| API            | 8000 | 18001 | 18000 |
| PostgreSQL     | 5432 |     — |     — |
| Twitch health  | 4344 |     — |     — |
| Discord health | 8080 |     — |     — |
| InstaFix       | 3002 |     — |     — |

所有已發布埠只綁 `127.0.0.1`。stg/prod API 埠僅供本機 tunnel agent 連入；前端由 Cloudflare Pages 建置發布，
`API_BACKEND` 指向後端。

`migrate` 容器在每次部署啟動時自動跑 DB migration。

### 舊 stack 一次性切換

第一個採用新 project 名稱的部署不會自動移除舊容器。deploy 若看到下列舊容器仍在執行會中止，避免兩個
PostgreSQL process 共用同一資料目錄或 Bot 重複上線：

| 環境 | 舊容器名稱                                                  | Tunnel 變更  |
| ---- | ----------------------------------------------------------- | ------------ |
| prod | `nb-api`、`nb-twitch`、`nb-discord`、`nb-pg`、`nb-instafix` | 8000 → 18000 |
| stg  | 上述名稱加 `-stg`                                           | 8001 → 18001 |

先以 stg 演練，再處理 prod。prod 維護窗流程：

```bash
# 1. 尚未停機前，用現行 DB 容器建立備份。
mkdir -p data/backups/prod
docker exec nb-pg sh -c 'exec pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "data/backups/prod/pre-compose-cutover-$(date +%Y%m%d-%H%M).sql.gz"

# 2. 停止但不刪除舊容器與 data；此時開始停機窗。
docker stop nb-api nb-twitch nb-discord nb-instafix nb-pg

# 3. 將 env 改為明確 prod 名稱，先 snapshot 再重排；碰到 source/target 並存會中止。
npm run nb -- env migrate prod
npm run nb -- env snapshot
npm run nb -- env sync prod
npm run nb -- env validate prod

# 4. 啟動隔離後的新 project，確認 health 後把 tunnel 改到 127.0.0.1:18000。
npm run nb -- stack prod build
npm run nb -- stack prod up full
curl -fsS http://127.0.0.1:18000/health
```

確認 API、DB 與兩個 Bot 正常後，才以 `docker rm` 明確移除已停止的舊容器；不要加 `-v`。若切換失敗，
先 `npm run nb -- stack prod down`，再以 `docker start nb-pg nb-instafix nb-api nb-twitch nb-discord`
恢復舊容器。stg 使用相同順序，但 selector、舊容器 suffix 與 tunnel port 改為表中數值。

## Twitch token encryption 與 Bot OAuth rollout

1. 先為 API 與 Twitch runtime 設定同一份長期保存的 `TWITCH_TOKEN_ENCRYPTION_KEY`；可用
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` 產生。不要在重新部署時重生。
2. 在 Twitch Developer Console 登記精確 callback：`<API_URL>/api/auth/twitch/bot/callback` 與
   `<API_URL>/api/auth/twitch/collaborator/callback`。
3. 備份資料庫後套用 migration 100–102；舊 token 暫時保持 `encryption_version=0`，服務仍可讀取。
4. 在含 `DATABASE_URL` 與 encryption key 的 backend 環境先執行：

   ```bash
   npm run nb -- stack prod exec api python -m scripts.twitch_ops.credentials --dry-run
   npm run nb -- stack prod exec api python -m scripts.twitch_ops.credentials --batch-size 100
   ```

5. 確認輸出 `remaining=0`，再依序重啟 API 與 Twitch bot。不可刪除舊 key；key rotation 需另做逐列 re-encrypt migration。
6. 先以 owner Twitch 帳號登入該環境一次，再由 `/admin` 建立 Niibot reset invite，或在運行目標
   Compose project 的 host 執行：

   ```bash
   npm run nb -- twitch invite stg
   npm run nb -- twitch invite prod
   ```

   命令只在所選 API container 內連線該環境 DB，輸出 30 分鐘有效的 invite URL 與到期時間；prod 會再次確認。
   將連結交給操作者並以指定 `BOT_ID` 帳號完成授權。invite URL 本身是一次性 bearer capability，不要寫入
   log 或貼到公開頻道。callback 成功後 runtime 透過 `bot_token_updated` 即時換 token。
   stg/prod 不使用本機 OAuth script；`npm run nb -- twitch oauth --env dev` 只供 localhost 開發。

若 Twitch runtime 回報 `Encrypted Twitch token is missing the v1 envelope`，代表至少一列資料標成
`encryption_version=1`，內容卻被舊 writer 以明文覆寫。先停止 restart loop、備份資料庫，再於持有同一份
`TWITCH_TOKEN_ENCRYPTION_KEY` 的 backend 環境執行 bounded repair；命令只回報列數，不輸出 token：

```bash
npm run nb -- stack prod exec api python -m scripts.twitch_ops.credentials \
  --repair-missing-envelopes --dry-run
npm run nb -- stack prod exec api python -m scripts.twitch_ops.credentials \
  --repair-missing-envelopes --batch-size 100
```

確認 `remaining=0` 後再啟動 Twitch runtime。不要手動把 `encryption_version` 改成 0，也不要在事故處理時更換
encryption key；若 repair 因 Fernet 驗證失敗而停止，應先確認部署載入的是原 key。

Rollback：Phase 2 schema 是 expand-only，可先關閉前端入口並回滾 application；不要回滾已加密資料欄位或換掉 key。
在同一 Twitch identity 同時作 broadcaster 與 Bot 前，授權 scopes 必須符合 union-scope 契約。

## Stack 管理

同一入口管理三個環境；`prod reset` 會被拒絕：

```bash
npm run nb -- stack stg up [profile]
npm run nb -- stack stg down
npm run nb -- stack stg reset
npm run nb -- stack stg build [service]
npm run nb -- stack stg logs [service]
npm run nb -- stack stg config
```

## CI/CD 密鑰

鍵清單由 [`env.registry.toml`](../../env.registry.toml) 產生（`npm run env:gen`）——
`.github/{secrets,variables}/*.env.example` 的**鍵**與 registry 對齊，值仍各環境手維護。

GitHub Actions 部署所需的值放在版本庫外的檔案，用腳本與 GitHub 同步：

```bash
# 首次：從範本建立
cp .github/secrets/base.env.example    .github/secrets/base.env
cp .github/secrets/prod.env.example    .github/secrets/prod.env
cp .github/secrets/stg.env.example     .github/secrets/stg.env
cp .github/variables/base.env.example    .github/variables/base.env
cp .github/variables/prod.env.example    .github/variables/prod.env
cp .github/variables/stg.env.example     .github/variables/stg.env

# 填值後推到 GitHub（prod = base + prod）
npm run nb -- env validate gh-prod
npm run nb -- env push prod

# 或從 GitHub 拉回現有值
npm run nb -- env pull prod
```

`pull` 不會讀取 secret 值，只回報名稱：`miss` 是未設定、`base-only` 是本應隔離到 GitHub
Environment 卻只存在 repo scope、`extra` 是 registry 已不再接受的名稱。`push` 會在任何遠端寫入前
檢查本機四個檔案；它不自動刪除遠端 extra，確認後用 `gh secret delete`／`gh variable delete`
明確移除。部署 writer 會以 literal dotenv quoting 寫值，並 URL-encode PostgreSQL DSN 元件。

公開 ID、URL、model 名稱與 runner path 放 Variables；password、token、client secret、API key、session
cookie 與 webhook 放 Secrets。若 registry 將既有 Secret 改列 Variable，GitHub API 無法讀回原值；須從權威
本機 env 重新填入 variable，驗證部署後再明確刪除同名 secret。分類搬遷前先執行
`npm run nb -- env snapshot`，不要把 `pull` 當成 secret 備份。

## 版本標記

部署工作流用 `git describe --tags --always` 產生執行期版本字串，前後端共用同一 tag。
tag 規範與 bump 時機見 [reference/versioning.md](../reference/versioning.md)。
