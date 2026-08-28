# 部署

三個環境、Docker Compose overlay、CI/CD 密鑰同步、版本標記。

## 分支與環境

| 分支                 | 環境   | 部署方式                                                               |
| -------------------- | ------ | ---------------------------------------------------------------------- |
| `main`               | 正式區 | `deploy-prod.yml`：手動 `workflow_dispatch` 或每週排程（基底映像更新） |
| `staging`            | 測試區 | `deploy-staging.yml`                                                   |
| `feature/*`、`fix/*` | 本機   | —                                                                      |

一般流程：`feature/xxx` ──PR──▶ `staging` ──(QA)──PR──▶ `main`。
Hotfix：`hotfix/xxx` ──PR──▶ `main` ──PR──▶ `staging`（backport）。

分支保護（於 GitHub 設定）：`main` 需 PR + 1 approval、禁止直推；`staging` 需 PR、允許 solo 直推。

## Docker Compose overlay

每個環境用 `docker-compose.yml`（base，不開主機埠）疊自己的 overlay：

```bash
# 正式
docker compose -f docker-compose.yml -f docker-compose.prod.yml [--profile <name>] up -d

# 測試（獨立 project／network／volume）
docker compose -p niibot-staging --env-file .env.staging \
  -f docker-compose.yml -f docker-compose.staging.yml [--profile <name>] up -d

# 本機
docker compose -f docker-compose.yml -f docker-compose.dev.yml [--profile <name>] up
```

Profile：`api` / `twitch` / `discord` / `bots` / `full`（見 [development.md](development.md)）。

對外埠：

| 服務     | 正式 | 本機 | 測試 |
| -------- | ---- | ---- | ---- |
| api      | 8000 | 8000 | 8001 |
| postgres | —    | 5433 | 5434 |
| instafix | —    | 3002 | 3004 |

正式區 API 埠僅供 Cloudflare Tunnel 連入；前端由 Cloudflare Pages 建置發布，
`API_BACKEND` 指向後端。

`migrate` 容器在每次部署啟動時自動跑 DB migration。

## Staging 管理

`scripts/staging.sh` 包好上面的長指令：

```bash
bash scripts/staging.sh up [profile]   # 啟動
bash scripts/staging.sh down            # 停止，保留 volume
bash scripts/staging.sh reset           # 停止並清除 volume
bash scripts/staging.sh build [service] # 重建映像
bash scripts/staging.sh logs [service]  # 追 log
```

## CI/CD 密鑰

GitHub Actions 部署所需的值放在版本庫外的檔案，用腳本與 GitHub 同步：

```bash
# 首次：從範本建立
cp .github/secrets/base.env.example    .github/secrets/base.env
cp .github/secrets/prod.env.example    .github/secrets/prod.env
cp .github/secrets/staging.env.example .github/secrets/staging.env
cp .github/variables/base.env.example    .github/variables/base.env
cp .github/variables/prod.env.example    .github/variables/prod.env
cp .github/variables/staging.env.example .github/variables/staging.env

# 填值後推到 GitHub（prod = base + prod）
bash .github/push.sh prod

# 或從 GitHub 拉回現有值
bash .github/pull.sh prod
```

## 版本標記

部署工作流用 `git describe --tags --always` 產生執行期版本字串，前後端共用同一 tag。
tag 規範與 bump 時機見 [reference/versioning.md](../reference/versioning.md)。
