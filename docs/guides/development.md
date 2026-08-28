# 本機開發

把 Niibot 在本機跑起來的兩條路：直接跑 Python／Node 程序，或用 Docker Compose。

## 1. 準備 env 檔

```bash
bash scripts/env.sh init      # 複製所有 *.env.example → *.env（已存在者略過）
bash scripts/env.sh init -f   # 強制覆蓋
```

接著填入各檔 secrets。欄位對照見 [environment.md](environment.md)。

`scripts/env.sh` 其他子命令：`snapshot` / `backup`（快照到 `data/`）、
`restore <日期|檔案>`、`diff`、`list`、`clean`。

## 2a. 直接跑程序

```bash
cd backend
uv sync --group dev
uv run python api/main.py        # API        :8000
uv run python twitch/main.py     # Twitch Bot  health :4344
uv run python discord/bot.py     # Discord Bot health :8080

cd frontend
npm install
npm run dev                      # 開發伺服器 :3000（代理 /api 到 :8000）
```

Postgres 可只開容器：`npm run dev:db`（背景啟動，對外 `:5433`）。

## 2b. 全部走 Docker Compose

所有 `npm run dev:*` 都疊 `docker-compose.yml` + `docker-compose.dev.yml`，
dev overlay 會把每個服務的埠對外。

| 指令                  | 內容                        |
| --------------------- | --------------------------- |
| `npm run dev:api`     | API + DB                    |
| `npm run dev:twitch`  | Twitch bot + DB             |
| `npm run dev:discord` | Discord bot + DB + Instafix |
| `npm run dev:bots`    | 兩個 bot + DB + Instafix    |
| `npm run dev:full`    | 全部                        |
| `npm run dev:db`      | 只開 DB（背景）             |
| `npm run dev:down`    | 停止全部                    |

底層等同 `docker compose --profile <name> up --build`。啟動時 `migrate` 容器會自動跑 DB migration。

> 前端不進 Docker——正式環境部署在 Cloudflare Pages，本機用 `npm run dev`。
> Threads sidecar（scrapling）也不在 Compose 內，見 [integrations/scrapling.md](../integrations/scrapling.md)。

## 3. 檢查與測試

root 的 `lint` / `format` / `typecheck` / `fix` / `test` 都是 fan-out，一次跑前後端；
也可以 `cd` 進單一資料夾只跑該側。

```bash
npm run lint          # 前端 ESLint      + 後端 ruff check
npm run format        # 前端 prettier    + 後端 ruff format
npm run typecheck     # 前端 tsc         + 後端 mypy
npm run fix           # 前端 eslint --fix + prettier、後端 ruff check --fix + ruff format
npm run test          # 前端 vitest --run + 後端 pytest（覆蓋率目標 80%+）
```

只跑單側：

```bash
cd frontend && npm run test:cov
cd backend  && uv run pytest
```

DB migration 手動執行：`cd backend && uv run python scripts/db_migrate.py`。
